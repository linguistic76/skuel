---
title: Feedback Architecture
updated: 2026-03-03
status: current
category: architecture
version: 2.0.0
tags:
- feedback
- activity_report
- submission_feedback
- activity_domains
- submissions
- exercise
related:
- FOUR_PHASED_LEARNING_LOOP.md
- ADR-038-content-sharing-model.md
- ADR-040-teacher-assignment-workflow.md
related_skills:
- learning-loop
---

# Feedback Architecture

> "The student submits, the system responds, the teacher refines."

SKUEL's feedback system is a unified response infrastructure covering two distinct entry points:

1. **Curriculum work** — a student submits against an Exercise; teacher or AI responds
2. **Activity Domains** — a user's Tasks, Goals, Habits, Events, Choices, and Principles; AI or admin responds

Both paths produce feedback entities. The `EntityType` and `ProcessorType` fields discriminate them.

---

## The Four EntityTypes

| EntityType | Who Creates | Purpose | ProcessorType |
|------------|-------------|---------|---------------|
| `SUBMISSION` | Student uploads file | Raw student work (audio, text, images) | `HUMAN` |
| `JOURNAL` | Admin uploads file | AI-processed reflective writing | `LLM` |
| `SUBMISSION_FEEDBACK` | Teacher **or** AI | Assessment with `subject_uid` pointing to the submission | `HUMAN` (teacher) or `LLM` (AI) |
| `ACTIVITY_REPORT` | System **or** Admin | Activity-level feedback (not tied to artifact) | `AUTOMATIC`, `LLM`, or `HUMAN` |

**Note:** `ACTIVITY_REPORT` does **not** inherit from `Submission`. It has no file fields. It inherits `UserOwnedEntity` directly and responds to a user's aggregate activity patterns over a time window.

---

## Naming Rationale

**SUBMISSION** (not "assignment") because:
- "Assignment" is what a **teacher gives** — that's an `Exercise` with `scope=ASSIGNED`
- "Submission" is what a **student uploads** — file content going through a processing pipeline
- Matches service names: `SubmissionsService`, protocol: `SubmissionOperations`
- Matches route language: `/submissions/submit`

---

## The Exercise (Curriculum Directive)

An `Exercise` is the teacher's directive — instructions for what students should produce.

```
Exercise (scope=ASSIGNED)
    |
    +-- instructions: str        # What to do (LLM prompt for AI feedback)
    +-- due_date: date           # When it's due
    +-- group_uid: str           # Which class
    +-- model: str               # Which LLM to use for AI feedback
```

**Two scopes:**
- `PERSONAL` — User's own AI template for self-directed feedback
- `ASSIGNED` — Teacher-created directive targeting a Group

---

## Curriculum Submission Pipeline

```
1. Teacher creates Exercise (scope=ASSIGNED, targets Group)
       |
       v
2. Student submits file → SubmissionsService.submit_file()
       |                   Creates Entity with entity_type=SUBMISSION
       v
3. Processing routes by MIME type (not EntityType):
       audio/* → TranscriptionService → text
       text/*  → Read raw content
       |
       v
4. Status transition: SUBMITTED → QUEUED → PROCESSING → COMPLETED
       |
       v
5. Auto-sharing: FULFILLS_EXERCISE + SHARES_WITH created
       |                             (student → teacher)
       v
6. Teacher reviews in queue → writes SUBMISSION_FEEDBACK
       |                       or requests REVISION
       v
7. Student sees feedback, optionally resubmits
```

### Relationship Graph

```cypher
// The exercise directive
(teacher:User)-[:OWNS]->(exercise:Exercise {scope: "assigned"})
(exercise)-[:FOR_GROUP]->(group:Group)
(student:User)-[:MEMBER_OF]->(group)

// The submission
(student)-[:OWNS]->(submission:Entity {entity_type: "submission"})
(submission)-[:FULFILLS_EXERCISE]->(exercise)

// Sharing for review
(student)-[:SHARES_WITH {role: "teacher"}]->(submission)

// Teacher feedback
(teacher)-[:OWNS]->(feedback:Entity {entity_type: "submission_feedback"})
(feedback)-[:FEEDBACK_FOR]->(submission)
```

---

## Two Entry Points, One Feedback Infrastructure

```
Curriculum Work                 Activity Domains
     │                               │
     ▼                               ▼
 SUBMISSION                     (no artifact —
 JOURNAL                         aggregate over
     │                            time window)
     │                               │
     └───────────┬───────────────────┘
                 │
                 ▼
           [FEEDBACK]
            ├── SUBMISSION_FEEDBACK  (response to a specific submission)
            └── ACTIVITY_REPORT      (response to activity patterns)
```

---

## Three Feedback EntityTypes

### 1. `SUBMISSION_FEEDBACK` — Response to a Specific Submission

`SUBMISSION_FEEDBACK` is created in response to a **specific submitted artifact** (a `SUBMISSION` or `JOURNAL` entity).

| Field | Value |
|-------|-------|
| `entity_type` | `"submission_feedback"` |
| Inherits | `Submission(UserOwnedEntity)` |
| `subject_uid` | UID of the submission being evaluated |
| `processor_type` | `HUMAN` or `LLM` |

**Two sources — same entity type:**

| Source | Service | ProcessorType | Trigger |
|--------|---------|---------------|---------|
| Teacher writes feedback | `SubmissionsCoreService.create_assessment()` | `HUMAN` | Teacher reviews submission in queue |
| AI evaluates via Exercise | `FeedbackService.generate_feedback()` | `LLM` | Exercise has `instructions`; AI generates response |

Both use atomic Cypher: create entity + `FEEDBACK_FOR` relationship + denormalize to `submission.feedback` in one transaction.

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(feedback:Entity:SubmissionFeedback {entity_type: 'submission_feedback'})
(feedback)-[:FEEDBACK_FOR]->(submission:Entity {entity_type: 'submission'})
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

| Source | Service | ProcessorType | Trigger |
|--------|---------|---------------|---------|
| Scheduled system | `ProgressFeedbackWorker` → `ProgressFeedbackGenerator` | `AUTOMATIC` | `ProgressSchedule` cron |
| On-demand AI | `ProgressFeedbackGenerator.generate()` | `LLM` | `POST /api/feedback/progress/generate` |
| Admin writes feedback | `ActivityReportService.submit_feedback()` | `HUMAN` | Admin reviews snapshot |

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
    processor_type: ProcessorType | None = None
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

## ProcessorType Taxonomy

`ProcessorType` discriminates the **source** of feedback, not the entity type:

| ProcessorType | Who | Applies To |
|---------------|-----|-----------|
| `HUMAN` | Teacher writes | `SUBMISSION_FEEDBACK` (teacher assessment) |
| `HUMAN` | Admin writes | `ACTIVITY_REPORT` (activity review) |
| `LLM` | AI via Exercise | `SUBMISSION_FEEDBACK` (AI assessment of submission) |
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
| `SubmissionsService` | `SubmissionOperations` | File upload, storage, submission record creation |
| `SubmissionsProcessingService` | `SubmissionProcessingOperations` | Routes files to processors, manages status transitions |
| `UnifiedSharingService` | `SharingOperations` | Visibility control, SHARES_WITH + SHARED_WITH_GROUP management |
| `TeacherReviewService` | `TeacherReviewOperations` | Review queue, human feedback, revision requests, approval |

**Feedback producers:**

| Service | Protocol | Produces | Notes |
|---------|----------|---------|-------|
| `SubmissionsCoreService` | `FeedbackOperations` | `SUBMISSION_FEEDBACK` (HUMAN) | Teacher assessment; verifies group membership |
| `FeedbackService` | `FeedbackOperations` | `SUBMISSION_FEEDBACK` (LLM) | AI evaluation via Exercise instructions |
| `ProgressFeedbackGenerator` | `ProgressFeedbackOperations` | `ACTIVITY_REPORT` (AUTOMATIC or LLM) | Activity summary; LLM adds qualitative insights |
| `ActivityReportService` | `ActivityReportOperations` | `ACTIVITY_REPORT` (HUMAN or via persist()) | Processor-neutral CRUD; all write paths converge here |
| `ReviewQueueService` | `ReviewQueueOperations` | `ReviewRequest` nodes | User-initiated review queue management |

**Graph intelligence (Level 1 — no LLM):**

| Service | Protocol | Responsibility |
|---------|----------|---------------|
| `FeedbackRelationshipService` | `FeedbackRelationshipOperations` | Pending submissions, feedback summary, learning loop chain traversal |

Methods: `get_pending_submissions()`, `get_unsubmitted_exercises()`, `get_feedback_summary()`, `get_learning_loop_chain(exercise_uid)`, `get_submission_chain(submission_uid)`. Used by `UserContextIntelligenceFactory`.

**Protocols:** `core/ports/feedback_protocols.py`

---

## Where Feedback Sits in the 4-Layer Architecture

The 5-phase learning loop is: **Article → Exercise → Submission → Feedback → RevisedExercise**

The first three stages are **leaf domains** — each owns its own Neo4j nodes and fits the standard 4-layer pattern:

```
*Operations protocol → *Backend subclass → *Service facade → sub-services

KuBackend          ← owns ORGANIZES, KU curriculum queries
ExerciseBackend    ← owns curriculum linking Cypher
SubmissionsBackend ← owns SHARES_WITH, access control Cypher
```

Feedback splits into two structurally different positions:

### SUBMISSION_FEEDBACK — Leaf Domain

`SUBMISSION_FEEDBACK` fits the leaf domain model. One submission goes in, one SubmissionFeedback node comes out. The generating services operate against a focused backend — the scope is a single artifact and its owner.

```
Submission  →  FeedbackService / SubmissionsCoreService  →  SUBMISSION_FEEDBACK node
               (one artifact in, one feedback node out)
```

### ACTIVITY_REPORT — Cross-Domain Aggregator

`ACTIVITY_REPORT` cannot fit the leaf domain model — it reads **across all 6 Activity Domain backends** to produce a synthesis.

```
Tasks + Goals + Habits + Events + Choices + Principles
    ↓ (historical completions, time window)
 ProgressFeedbackGenerator
    ↓ (LLM or programmatic markdown)
ACTIVITY_REPORT node
```

`ProgressFeedbackGenerator` accepts a `UserContextBuilder` (primary data source) alongside a `QueryExecutor` (annotation lookup only). The primary data comes from `context_builder.build_rich(user_uid, window=...)` — MEGA_QUERY extended with six activity-window CALL{} blocks. Per SKUEL's architecture rule: **domain-specific Cypher belongs on the domain backend; cross-domain aggregation stays in services.** `ProgressFeedbackGenerator` is the cross-domain aggregation service — it sits above the domain backends by design.

This is why it does not have a `FeedbackBackend` with domain-specific Cypher methods. The `build_rich()` result (`context.entities_rich`, `context.knowledge_units_rich`, `context.enrolled_paths_rich`, `context.active_learning_steps_rich`) gives the full cross-domain picture in a single Neo4j round-trip.

### Summary

| Feedback Mode | Structural Position | Why |
|---------------|--------------------|----|
| `SUBMISSION_FEEDBACK` | Leaf domain — fits 4-layer pattern | One artifact in, one node out; single-domain scope |
| `ACTIVITY_REPORT` | Cross-domain aggregator — sits above domain backends | Reads from 6 Activity Domain backends; no single domain owns it |

The learning loop does not end at a leaf domain — it fans back out across the user's entire lived activity. That is what makes `ACTIVITY_REPORT` architecturally distinct from the other three stages of the loop.

---

## UI Surfaces

**Curriculum track:**

| Route | Who | What |
|-------|-----|------|
| `/submissions/submit` | Student | Upload files for processing |
| `/submissions/{uid}` | Owner | View submission, sharing controls |
| `/journals/submit` | Admin | Upload files for AI (LLM) processing |
| `/profile/shared` | Any user | "Shared With Me" inbox |
| `/api/teaching/review-queue` | Teacher | Pending submission review queue |
| `/api/teaching/review/{uid}/feedback` | Teacher | Submit human feedback on submission |
| `/api/teaching/review/{uid}/approve` | Teacher | Approve submission |

**Activity feedback track:**

| Route | Who | What |
|-------|-----|------|
| `/api/feedback/progress` | User | List user's `ACTIVITY_REPORT` history |
| `/api/feedback/progress/generate` | User | On-demand `ACTIVITY_REPORT` generation |
| `/api/activity-review/snapshot` | Admin | Generate activity snapshot for review |
| `/api/activity-review/submit` | Admin | Submit written activity feedback |
| `/api/activity-review/request` | User | Request an activity review from admin |
| `/api/activity-review/queue` | Admin | Pending review queue |
| `/api/activity-review/history` | User/Admin | Received activity feedback history |
| `/api/privacy/audit` | User | Privacy transparency summary (admin snapshots, shares, schedule) |

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
POST /api/activity-review/submit → ActivityReportService.submit_feedback()
        ↓  (calls ActivityReportService.persist() — all writes converge here)
ActivityReport(ProcessorType.HUMAN) created in Neo4j
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

## LLM Feedback Generation (`ProgressFeedbackGenerator`)

When `openai_service` is available, the generator:

1. Calls `context_builder.build_rich(user_uid, window=time_period)` — MEGA_QUERY extended with 6 activity window CALL{} blocks; `context.entities_rich` contains all domains (same method used by `ActivityReportService.create_snapshot()`)
2. Cross-references active Insights
3. Checks cooldown: if the user has generated a report within the last `FeedbackTimePeriod.MIN_REPORT_COOLDOWN_MINUTES` (60 min), returns a business error rather than calling the LLM (rate limit)
4. Fetches `user_annotation` from the most recent prior `ActivityReport` (`period_end < current_period_start`) via `_fetch_previous_annotation()`
5. Sends stats as JSON context to LLM via `activity_feedback.md` prompt template; if a prior annotation exists, appends it inside explicit injection-guard boundaries (`--- USER REFLECTION ... --- END USER REFLECTION ---`) with an instruction to treat it as user voice only — not instructions
6. LLM returns qualitative analysis with patterns, trends, recommendations
7. Creates `ActivityReport` with `processed_content = LLM output`, `metadata = raw stats`

**Graceful fallback:** If LLM call fails, falls back to programmatic markdown with `ProcessorType.AUTOMATIC` and logs `processing_error`. If no prior annotation exists, the prompt is unchanged.

**Annotation feedback loop:** User annotations flow back into the next report's LLM prompt via `_fetch_previous_annotation()`. The field is also surfaced in `UserContext.latest_activity_report_user_annotation` and included in Askesis's `build_llm_context()` when the query mentions feedback/patterns/reflection keywords.

**Prompt template:** `core/prompts/templates/activity_feedback.md`

---

## API Routes

| Route | Method | Who | What |
|-------|--------|-----|------|
| `/api/activity-reports/annotate` | POST | User | Save annotation or revision to own report |
| `/api/activity-reports/annotation` | GET | User | Get current annotation state for a report |
| `/api/feedback/progress/generate` | POST | User | On-demand `ACTIVITY_REPORT` generation |
| `/api/feedback/progress` | GET | User | List user's `ACTIVITY_REPORT` history |
| `/api/feedback/schedule` | POST | User | Create/update generation schedule |
| `/api/feedback/schedule/get` | GET | User | Get user's schedule |
| `/api/feedback/schedule/update` | POST | User | Update schedule |
| `/api/feedback/schedule/delete` | POST | User | Deactivate schedule |
| `/api/activity-review/snapshot` | GET | Admin | Generate activity snapshot for review |
| `/api/activity-review/submit` | POST | Admin | Submit written activity feedback |
| `/api/activity-review/request` | POST | User | Request an activity review from admin |
| `/api/activity-review/queue` | GET | Admin | Pending review queue |
| `/api/activity-review/history` | GET | User/Admin | Received activity feedback history |
| `/api/feedback/assessments` | POST | Teacher | Create teacher assessment (`SUBMISSION_FEEDBACK`) |
| `/api/feedback/assessments/for-student` | GET | Teacher | Student's received assessments |
| `/api/feedback/assessments/by-teacher` | GET | Teacher | Teacher's authored assessments |
| `/api/teaching/review-queue` | GET | Teacher | Pending submission review queue |
| `/api/teaching/review/{uid}/feedback` | POST | Teacher | Submit human feedback on submission |
| `/api/teaching/review/{uid}/approve` | POST | Teacher | Approve submission |

---

## Neo4j Schema

```cypher
// SUBMISSION_FEEDBACK — tied to a specific submission
(:Entity:SubmissionFeedback {
    uid, entity_type: 'submission_feedback',
    user_uid,        // owner (teacher or AI agent)
    subject_uid,     // submission being evaluated
    processor_type,  // 'human' or 'llm'
    title, processed_content,
    created_at, updated_at
})

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
ProgressFeedbackGenerator.generate(user_uid, time_period="7d")
    → Injects context_builder: UserContextBuilder
    → Calls build_rich() for cross-domain snapshot
    → Checks cooldown (FeedbackTimePeriod.MIN_REPORT_COOLDOWN_MINUTES)
    → Fetches prior annotation via _fetch_previous_annotation()
    → Sends to LLM via activity_feedback.md prompt template
    → Fallback: programmatic markdown with ProcessorType.AUTOMATIC
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

**Key constraint:** `ProgressFeedbackGenerator` is a cross-domain aggregator — it sits above domain backends by design. It does not have a `FeedbackBackend` with domain-specific Cypher. The `build_rich()` result provides the full cross-domain picture in a single query.

---

## See Also

- [FOUR_PHASED_LEARNING_LOOP.md](/docs/architecture/FOUR_PHASED_LEARNING_LOOP.md) — Entry-point overview: two tracks, four phases, how MEGA_QUERY feeds the loop
- [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)
- [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md)
- [Entity Type Architecture](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)
- [Sharing Patterns](/docs/patterns/SHARING_PATTERNS.md)
