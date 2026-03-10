---
name: learning-loop
description: >
  Expert guide for SKUEL's Five-Phased Learning Loop — the core purpose of the app.
  Use when building or reviewing any feature involving Article, Exercise, Submission, Report,
  or RevisedExercise. TRIGGER when: working on submissions, exercises, report generation,
  activity reports, revised exercises, teacher review, AI assessment, or when designing a new
  feature and asking "where does this fit?". This skill provides the development lens: every
  new feature must either strengthen a loop phase or improve the transition between phases.
  Features that serve no loop purpose are candidates for deletion per SKUEL's One Path Forward
  philosophy.
allowed-tools: Read, Grep, Glob
---

# The Five-Phased Learning Loop

> "Knowledge is learned by doing, evaluated by responding, and refined by reflecting."

The Five-Phased Learning Loop is the **core purpose of SKUEL**. Every feature in the
codebase either feeds this loop, supports its infrastructure, or should be questioned.
Understanding the loop is the prerequisite for all architectural decisions.

---

## The Loop at a Glance

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    FIVE-PHASED LEARNING LOOP                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  CURRICULUM TRACK (artifact-based)                                       ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Article] → [Exercise] → [Submission/Journal] → [Report]               ║
║   ↑             ↓              ↑↓                     ↓                  ║
║  admin       teacher        student               teacher/AI             ║
║  creates     assigns     uploads/revises          assesses               ║
║                                                      ↓                   ║
║                                              [RevisedExercise]           ║
║                                               teacher creates            ║
║                                              targeted revision           ║
║                                                      ↓                   ║
║                                              [Submission v2] → ...       ║
║                                                                          ║
║  ACTIVITY TRACK (aggregate-based)                                        ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Tasks + Goals + Habits + Events + Choices + Principles]                ║
║                    ↓ (over time window)                                   ║
║             [Activity Report] ←── AI or Admin                            ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

**Two tracks, one loop.** Activity Domains are equal entry points — a user's lived
practice (Tasks, Goals, Habits) receives the same feedback infrastructure as curriculum
work. The mechanism differs (`ACTIVITY_REPORT` vs `SUBMISSION_REPORT`), but both
close the loop: student does work, system or teacher responds.

---

## Field Naming Convention: `entity_type` vs `EntityType`

The Python enum is named `EntityType`. The Python model field and Neo4j node
property are both named **`entity_type`** (renamed from `ku_type` in March 2026).

```python
# Python model field:
ku = Ku(entity_type=EntityType.KU, ...)
report = ExerciseReport(entity_type=EntityType.EXERCISE_REPORT, ...)
activity_report = ActivityReport(entity_type=EntityType.ACTIVITY_REPORT, ...)

# Neo4j property:
MATCH (n:Entity {entity_type: 'exercise_report'})
MATCH (n:Entity {entity_type: 'ku'})
```

---

## Phase 1: Ku — The Knowledge Unit

**What it is:** Atomic curriculum content. A single "brick" of knowledge, admin-created
and shared across all users. The curriculum track begins here.

**EntityType:** `EntityType.KU`
**Model:** `core/models/ku/ku.py` — `Ku(Curriculum)` frozen dataclass
**DTO:** `core/models/ku/ku_dto.py`
**UID format:** `ku_{slug}_{random}`
**Neo4j label:** `:Entity:Ku`

**Key fields:**
```python
title: str                        # The knowledge unit's name
content: str                      # Substance — what to learn
domain: str                       # Which knowledge domain
complexity: KuComplexity          # BASIC / INTERMEDIATE / ADVANCED / EXPERT
learning_level: LearningLevel     # K-12 / UNDERGRAD / GRAD / PROFESSIONAL
status: EntityStatus              # DRAFT → ACTIVE → ARCHIVED
```

**Access:** `ContentScope.SHARED` — admins create, all users read. No ownership check.

**Services:**
```python
services.ku                       # KuService facade (8 sub-services)
services.ku.core                  # CRUD — create, update, delete
services.ku.search                # search(), get_by_status(), get_by_category()
services.ku.organization          # ORGANIZES relationships (MOC pattern)
services.ku.intelligence          # get_ku_with_context(), readiness scoring
```

**Graph pattern:**
```cypher
(admin:User)-[:OWNS]->(ku:Entity:Ku {uid, title, content, complexity})
(ku)-[:ORGANIZES {order: 1}]->(child_ku:Entity:Ku)  // MOC: any Ku can organize others
(exercise)-[:REQUIRES_KNOWLEDGE]->(ku)               // Exercise links to required Ku
```

**Loop role:** Ku is the *why* — the knowledge the loop exists to transmit. Every
Exercise is grounded in one or more Ku nodes. When a student completes an Exercise,
they are demonstrating engagement with specific Ku content.

---

## Phase 2: Exercise — The Assignment

**What it is:** The teacher's directive. Instructions for what students should produce,
with an LLM prompt embedded for AI-assisted feedback.

**EntityType:** `EntityType.EXERCISE`
**Model:** `core/models/exercises/exercise.py` — `Exercise(Curriculum)` frozen dataclass
**DTO:** `core/models/exercises/exercise_dto.py`
**Neo4j label:** `:Entity:Exercise`

**Key fields:**
```python
instructions: str                 # Teacher's directive — ALSO used as LLM prompt
model: str                        # LLM to use: "claude-sonnet-4-6"
scope: ExerciseScope              # PERSONAL (self-directed) | ASSIGNED (classroom)
due_date: date | None             # ASSIGNED only — when submission is due
group_uid: str | None             # ASSIGNED only — which class receives this
enrichment_mode: str | None       # Processing strategy for the submission
context_notes: tuple[str, ...]    # Reference materials (immutable)
form_schema: tuple[dict, ...] | None  # Inline form definition for structured submissions
```

**Two submission modes:**

| Mode | `form_schema` | Student action | Submission content |
|------|--------------|----------------|-------------------|
| **File upload** | `None` | Uploads file (audio, text, image) | `file_path`, `processed_content` |
| **Inline form** | Present | Fills embedded form in article | `metadata["form_data"]`, `processed_content` (JSON) |

When `form_schema` is set, the article reading page renders the form inline. Both modes
create `ExerciseSubmission` and trigger the same event pipeline (`FULFILLS_EXERCISE`,
auto-share with teacher).

**Two scopes:**

| Scope | Created by | Targets | Due date | Purpose |
|-------|-----------|---------|----------|---------|
| `PERSONAL` | User | Self | Optional | Self-directed AI feedback |
| `ASSIGNED` | Teacher | Group | Required | Teacher assigns to class |

**Services:**
```python
services.exercises                # ExerciseService facade
services.exercises.core           # CRUD; ExerciseBackend for Cypher
```

**Backend (domain-specific Cypher):**
```python
# ExerciseBackend — domain-specific relationship Cypher
await backend.link_to_curriculum(exercise_uid, ku_uid)      # REQUIRES_KNOWLEDGE
await backend.unlink_from_curriculum(exercise_uid, ku_uid)  # DELETE relationship
await backend.get_required_knowledge(exercise_uid)          # list KUs required
await backend.get_exercise_for_submission(submission_uid)   # FULFILLS_EXERCISE lookup
```

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(exercise:Entity:Exercise {
    scope: 'assigned',
    instructions: '...',         // This IS the LLM prompt for feedback generation
    model: 'claude-sonnet-4-6',
    group_uid: 'group_abc123'
})
(exercise)-[:FOR_GROUP]->(group:Group)           // classroom targeting
(exercise)-[:REQUIRES_KNOWLEDGE]->(ku:Entity:Ku) // which Ku this exercise covers
```

**Loop role:** Exercise is the *how* — it operationalizes Ku into a concrete task.
Its `instructions` field serves double duty: directive for the student AND prompt for
the AI when generating feedback. This is the bridge between knowledge and evaluation.

---

## Phase 3: Submission — The Student's Work

**What it is:** The student's artifact. An uploaded file (audio, text, image) that is
processed and then evaluated. Two leaf types share the same base model.

**EntityTypes:** `EntityType.EXERCISE_SUBMISSION` and `EntityType.JOURNAL_SUBMISSION`
**Models:** `ExerciseSubmission(Submission)` and `JournalSubmission(Submission)` — frozen dataclasses
**Base:** `core/models/submissions/submission.py` — `Submission(UserOwnedEntity)`
**Neo4j labels:** `:Entity:ExerciseSubmission:Submission` or `:Entity:JournalSubmission:Submission`

**Key fields:**
```python
# File storage
original_filename: str | None
file_path: str | None
file_size: int | None
file_type: str | None             # MIME type: "audio/mpeg", "text/plain"

# Processing pipeline
processor_type: ProcessorType | None   # HUMAN | LLM
processing_started_at: datetime | None
processing_completed_at: datetime | None
processing_error: str | None
processed_content: str | None    # Transcribed/enriched text — the evaluable content
instructions: str | None         # Processing directives (from Exercise)

# Subject (for feedback entities only)
subject_uid: str | None          # UID of the submission being evaluated
```

**Two leaf types:**

| EntityType | Created by | ProcessorType | Processing |
|-----------|-----------|---------------|-----------|
| `SUBMISSION` | Student uploads | `HUMAN` (then LLM feedback) | Transcription if audio |
| `JOURNAL` | Admin uploads | `LLM` | Auto-processed, AI uses Exercise instructions |

**Processing pipeline (two entry points):**
```
FILE UPLOAD PATH                          INLINE FORM PATH
Student uploads file                      Student fills form in article page
        ↓                                         ↓
SubmissionsService.submit_file()          SubmissionsService.submit_form()
 → file stored to disk                    → form_data in metadata + processed_content
 → Entity with status: SUBMITTED          → Entity with status: SUBMITTED
        ↓                                         ↓
Route by MIME type:                       (no processing needed — data is structured)
  audio/* → TranscriptionService                  ↓
  text/*  → Read raw content              ┌───────┘
        ↓                                 ↓
Status: PROCESSING → COMPLETED      SubmissionCreated event fires:
        ↓                             FULFILLS_EXERCISE (Submission → Exercise)
SubmissionCreated event fires:        SHARES_WITH {role: 'teacher'} (if ASSIGNED)
  Same as form path →
```

**API routes:**
- `POST /api/submissions/upload` — file upload (multipart form-data)
- `POST /api/submissions/form` — structured form data (JSON: `{exercise_uid, form_data}`)

**Services:**
```python
services.submissions              # SubmissionsService facade
services.submissions_core         # SubmissionsCoreService — CRUD, exercise linking
services.submissions_processor    # Processing pipeline — transcription, enrichment
```

**Backend (domain-specific Cypher):**
```python
# SubmissionsBackend — owns all SHARES_WITH Cypher
await backend.share_submission(entity_uid, owner_uid, recipient_uid, role)
await backend.unshare_submission(entity_uid, owner_uid, recipient_uid)
await backend.get_shared_with_users(entity_uid)
await backend.set_visibility(entity_uid, owner_uid, visibility)
await backend.check_access(entity_uid, user_uid)         # owner OR shares_with
```

**Access:** `ContentScope.USER_OWNED`. Default `PRIVATE`. Sharing via
`UnifiedSharingService` — three-level model: `PRIVATE → SHARED → PUBLIC`.

**Loop role:** Submission is the *evidence* — the student's demonstration of engagement
with the Ku. The `processed_content` field is what AI and teachers actually evaluate.
Without Submission, the loop has no student voice.

---

## Phase 4: Report — The Response

**What it is:** The evaluation. Two structurally distinct entities cover two distinct
entry points. Both close the loop — both say "here is what your work means."

### 4a. SUBMISSION_REPORT — Response to an Artifact

**EntityType:** `EntityType.SUBMISSION_REPORT`
**Model:** `core/models/report/submission_report.py` — `SubmissionReport(Submission)` frozen dataclass
**Neo4j label:** `:Entity:SubmissionReport`
**Inherits:** Full `Submission` model (+2 report-specific fields)

**Key fields:**
```python
subject_uid: str | None          # UID of the submission being evaluated (inherited)
processor_type: ProcessorType    # HUMAN (teacher) | LLM (AI)
feedback: str | None             # The evaluation text
feedback_generated_at: datetime | None
```

**Two sources — same EntityType, different ProcessorType:**

| Source | Service | ProcessorType | Trigger |
|--------|---------|---------------|---------|
| Teacher | `SubmissionsCoreService.create_assessment()` | `HUMAN` | Teacher reviews in queue |
| AI | `SubmissionReportService.generate_report()` | `LLM` | Exercise has `instructions` |

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(report:Entity:SubmissionReport {
    subject_uid: 'submission_uid_being_evaluated',
    processor_type: 'human',     // or 'llm'
    feedback: 'Your analysis shows...'
})
(report)-[:FEEDBACK_FOR]->(submission:Entity:Submission)
```

**Structural position:** Leaf domain. One submission in, one report node out.
Fits the standard 4-layer pattern: `SubmissionReportOperations` protocol → `SubmissionsBackend`
→ `SubmissionReportService` / `SubmissionsCoreService` → sub-services.

**The Revision Cycle (Phase 4 → 3 → 4):**

After reviewing a submission, the teacher has three outcomes via `TeacherReviewService`
(`core/services/report/teacher_review_service.py`, protocol: `TeacherReviewOperations`
in `core/ports/report_protocols.py`):

| Action | Method | Event Published | Result |
|--------|--------|-----------------|--------|
| Write report | `submit_report()` | `ReportSubmitted` | `SubmissionReport` created, loop continues |
| Request revision | `request_revision()` | `SubmissionRevisionRequested` | Student notified, resubmit expected |
| Approve | `approve_report()` | `SubmissionApproved` | Loop closes for this exercise |

Each feedback round creates a new `SubmissionReport` entity via `FEEDBACK_FOR` —
revision cycles are traceable as first-class graph entities. The loop publishes
`ReportSubmitted`, `SubmissionRevisionRequested`, and `SubmissionApproved` events.
Student notification delivery is **planned** — see the Messaging system in
`CLAUDE.md`. Students currently need to poll `/submissions/feedback` or the
activity feed to discover new feedback.

---

### 4b. ACTIVITY_REPORT — Response to Activity Patterns

**EntityType:** `EntityType.ACTIVITY_REPORT`
**Model:** `core/models/report/activity_report.py` — `ActivityReport(UserOwnedEntity)` frozen dataclass
**Neo4j label:** `:Entity:ActivityReport`
**Inherits:** `UserOwnedEntity` **directly** — NO file fields by design

**Key fields:**
```python
processor_type: ProcessorType | None    # AUTOMATIC | LLM | HUMAN
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

| Source | Service | ProcessorType | Trigger |
|--------|---------|---------------|---------|
| Scheduled system | `ProgressReportWorker` → `ProgressReportGenerator` | `AUTOMATIC` | Cron schedule |
| On-demand AI | `ProgressReportGenerator.generate()` | `LLM` | User requests via API |
| Admin writes | `ActivityReportService.submit_report()` | `HUMAN` | Admin reviews snapshot |

**Structural position:** Cross-domain aggregator. Cannot fit the leaf domain model
because it reads across all 6 Activity Domain backends **and** the Curriculum track
(KU mastery, LP progress, active LS). `ProgressReportGenerator` accepts a
`UserContextBuilder` and calls `build_rich(user_uid, window=...)` — MEGA_QUERY
with activity window CALL{} blocks. This gives the generator access to full graph
neighbourhoods across both tracks. `ActivityReportService.create_snapshot()` uses
the same method.

**LLM generation flow:**
```
1. Call `context_builder.build_rich(user_uid, time_period=...)` — MEGA_QUERY with
   activity window; `context.entities_rich` covers all 6 Activity Domains;
   `context.knowledge_units_rich`, `context.enrolled_paths_rich`,
   `context.active_learning_steps_rich` cover the Curriculum track
2. Cross-reference active Insights
3. Send stats as JSON context to LLM via activity_feedback.md prompt template
4. LLM returns qualitative analysis with patterns, trends, recommendations
5. Create ActivityReport with processed_content = LLM output
6. Graceful fallback: if LLM fails → ProcessorType.AUTOMATIC + programmatic markdown
```

**Prompt template:** `core/prompts/templates/activity_feedback.md`

---

## Phase 5: RevisedExercise — The Targeted Revision

**What it is:** A teacher-created revision of an Exercise that addresses specific gaps
identified in `SubmissionReport`. Forces a reflection step between feedback and
resubmission.

```
Article → Exercise v1 → Submission v1 → SubmissionReport v1
                                              ↓
                                        RevisedExercise v2 → Submission v2 → ...
```

**EntityType:** `EntityType.REVISED_EXERCISE`
**Model:** `core/models/exercises/revised_exercise.py` — `RevisedExercise(UserOwnedEntity)` frozen dataclass
**DTO:** `core/models/exercises/revised_exercise_dto.py`
**Neo4j label:** `:Entity:RevisedExercise`

**Key design:**
- Inherits `UserOwnedEntity` (NOT Curriculum) — needs `user_uid` but not 21 Curriculum fields
- First entity type combining `ContentOrigin.CURRICULUM` with `requires_user_uid()=True`
- Teacher-owned, student-targeted (student visibility via `student_uid` field)
- `revision_number` auto-determined from existing chain length

**Services:**
```python
services.revised_exercises              # RevisedExerciseService — CRUD + chain queries
```

**Backend:**
```python
# RevisedExerciseBackend — domain-specific relationship Cypher
await backend.link_to_report(re_uid, report_uid)           # RESPONDS_TO_REPORT
await backend.link_to_exercise(re_uid, exercise_uid)      # REVISES_EXERCISE
await backend.get_revision_chain(exercise_uid)             # All revisions ordered
```

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(re:Entity:RevisedExercise {
    original_exercise_uid: '...',
    student_uid: '...',
    revision_number: 2
})
(re)-[:RESPONDS_TO_REPORT]->(report:Entity:SubmissionReport)
(re)-[:REVISES_EXERCISE]->(exercise:Entity:Exercise)
(submission:Entity:Submission)-[:FULFILLS_EXERCISE]->(re)  // reuses existing rel type
```

**Event:** `RevisedExerciseCreated` (`revised_exercise.created`) — published on creation,
enables student notification and learning loop progression tracking.

**Access control:**
- **Create:** `create_revised_exercise` verifies the teacher has `SHARES_WITH {role:'teacher'}`
  on the submission linked to the report, and the `student_uid` owns that submission.
  Graph path checked: `(Teacher)-[:SHARES_WITH]->(Submission)<-[:FEEDBACK_FOR]-(Report)` +
  `(Student)-[:OWNS]->(Submission)`. Prevents teachers from creating revisions targeting
  arbitrary students' feedback.
- **List for student (teacher route):** `list_for_student(student_uid, teacher_uid=)` scopes
  results to revisions owned by the requesting teacher, preventing cross-teacher leakage.
- **Student access:** On creation, a `SHARES_WITH {role: 'student'}` relationship is auto-created
  from the student to the RevisedExercise. Students discover revisions through:
  - "Shared With Me" inbox (SHARES_WITH relationship)
  - `GET /api/revised-exercises/my-revisions` (student_uid match)
  - `GET /api/revised-exercises/view?uid=` (student_uid or owner match)
  - Daily planning: `get_ready_to_work_on_today()` surfaces them at Priority 2.3 via
    `context.pending_revised_exercises` (populated by MEGA-QUERY)

**Loop role:** RevisedExercise is the *refinement* — it bridges feedback back into a
new exercise, closing the revision cycle explicitly rather than implicitly.

---

## The Binding Graph Relationships

| Relationship | Connects | Purpose |
|---|---|---|
| `REQUIRES_KNOWLEDGE` | `Exercise` → `Ku` | Exercise is grounded in this knowledge |
| `FOR_GROUP` | `Exercise` → `Group` | ASSIGNED exercise targets this classroom |
| `FULFILLS_EXERCISE` | `Submission` → `Exercise` or `RevisedExercise` | Student's work satisfies this exercise |
| `SHARES_WITH` | `Submission` → `User` | Auto-share to teacher for ASSIGNED exercises |
| `SHARES_WITH` | `User` → `RevisedExercise` | Auto-share revision to student on creation |
| `FEEDBACK_FOR` | `SubmissionReport` → `Submission` | Report evaluates this specific artifact |
| `RESPONDS_TO_REPORT` | `RevisedExercise` → `SubmissionReport` | Revision addresses this report |
| `REVISES_EXERCISE` | `RevisedExercise` → `Exercise` | Revision of this original exercise |

**RelationshipName enum locations:**
```python
from core.models.enums.relationship_names import RelationshipName

RelationshipName.REQUIRES_KNOWLEDGE      # Exercise → Ku
RelationshipName.FOR_GROUP               # Exercise → Group
RelationshipName.FULFILLS_EXERCISE       # Submission → Exercise (or RevisedExercise)
RelationshipName.SHARES_WITH             # Submission → User (also group sharing)
RelationshipName.REPORT_FOR              # SubmissionReport → Submission
RelationshipName.SHARED_WITH_GROUP       # Submission → Group (group sharing)
RelationshipName.RESPONDS_TO_REPORT     # RevisedExercise → SubmissionReport
RelationshipName.REVISES_EXERCISE        # RevisedExercise → Exercise
```

---

## Service Architecture Summary

| Phase | Service | Protocol | Backend | Key Methods |
|-------|---------|----------|---------|-------------|
| **Ku** | `KuService` | `KuOperations` | `KuBackend` | `organize`, `get_subkus`, CRUD |
| **Exercise** | `ExerciseService` | `ExerciseOperations` | `ExerciseBackend` | `link_to_curriculum`, `get_exercise_for_submission`, `get_student_exercises`, `get_student_exercises_with_status`, CRUD |
| **RevisedExercise** | `RevisedExerciseService` | `RevisedExerciseOperations` | `RevisedExerciseBackend` | CRUD, `list_for_teacher`, `list_for_student`, `get_revision_chain` |
| **Submission** | `SubmissionsService` | `SubmissionOperations` | `SubmissionsBackend` | `submit_file`, `check_access`, share methods |
| **Submission processing** | `SubmissionsProcessingService` | `SubmissionProcessingOperations` | `SubmissionsBackend` | Processing pipeline |
| **Submission report** | `SubmissionReportService` + `SubmissionsCoreService` | `SubmissionReportOperations` | `SubmissionsBackend` | `generate_report`, `create_assessment` |
| **Teacher review** | `TeacherReviewService` | `TeacherReviewOperations` | `QueryExecutor` | **Review actions:** `get_review_queue`, `get_submission_detail`, `get_report_history`, `submit_report`, `request_revision`, `approve_report` · **Exercise view:** `get_exercises_with_submission_counts`, `get_submissions_for_exercise` · **Student view:** `get_students_summary`, `get_student_submissions` · **Dashboard:** `get_dashboard_stats`, `get_teacher_groups_with_stats`, `get_group_detail` |
| **Activity Report (auto/LLM)** | `ProgressReportGenerator` | `ProgressReportOperations` | `UserContextBuilder` | `generate`, `create_scheduled` |
| **Activity Report (scheduled)** | `ProgressReportWorker` | — | — | Background worker; calls `ProgressReportGenerator` on schedule |
| **Activity Report (schedule CRUD)** | `ProgressScheduleService` | `ProgressScheduleOps` | — | `get_schedules`, `create_schedule`, `delete_schedule` |
| **Activity Report (human)** | `ActivityReportService` | `ActivityReportOperations` | `UserContextBuilder` | `create_snapshot`, `submit_report`, `persist`, `get_history`, `annotate` |

**Protocols location:** `core/ports/report_protocols.py` (all report + teacher review), `core/ports/submission_protocols.py`, `core/ports/group_protocols.py` (group CRUD only)

---

## API Routes Per Phase

| Phase | Route | Method | Who |
|-------|-------|--------|-----|
| **Student assignments** | `/submissions/assignments` | GET | Student |
| **Submission** | `/submissions/submit` | POST | Student |
| **Submission detail** | `/submissions/{uid}` | GET | Student (owner) |
| **Submission feedback** | `/submissions/{uid}/feedback` | GET (HTMX) | Student (owner) |
| **Submission exercise link** | `/submissions/{uid}/exercise` | GET (HTMX) | Student |
| **Submission** | `/api/submissions/...` | GET/POST | Student |
| **Submission sharing** | `/api/share/group` | POST | Student |
| **Submission sharing** | `/api/submissions/shared-with-me` | GET | Teacher |
| **Submission report** | `/api/reports/assessments` | POST | Teacher |
| **Submission report** | `/api/reports/assessments/given` | GET | Teacher |
| **Submission report** | `/api/reports/assessments/received` | GET | Student |
| **Student feedback UI** | `/submissions/feedback` | GET | Student |
| **Teacher review** | `/api/teaching/review-queue` | GET | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}` | GET | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/feedback` | POST | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/revision` | POST | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/approve` | POST | Teacher |
| **Teacher exercises** | `/api/teaching/exercises` | GET | Teacher |
| **Teacher exercises** | `/api/teaching/exercises` | POST | Teacher |
| **Teacher exercises** | `/api/teaching/exercises/{uid}` | POST | Teacher |
| **Teacher exercises** | `/api/teaching/exercises/{uid}/submissions` | GET | Teacher |
| **Teacher students** | `/api/teaching/students` | GET | Teacher |
| **Teacher students** | `/api/teaching/students/{uid}/submissions` | GET | Teacher |
| **Teacher dashboard** | `/api/teaching/dashboard` | GET | Teacher |
| **Teacher classes** | `/api/teaching/classes` | GET | Teacher |
| **Teacher classes** | `/api/teaching/classes/{uid}` | GET | Teacher |
| **Notifications** | `/notifications` | GET | Student — **planned, not yet implemented** |
| **Activity report** | `/api/reports/progress/generate` | POST | User |
| **Activity report** | `/api/reports/progress` | GET | User |
| **Activity report** | `/api/reports/schedule` | POST | User |
| **Activity review (admin)** | `/api/activity-review/snapshot` | GET | Admin |
| **Activity review (admin)** | `/api/activity-review/submit` | POST | Admin |
| **Activity review (admin)** | `/api/activity-review/queue` | GET | Admin |
| **Activity review (user)** | `/api/activity-review/history` | GET | User |
| **Annotation** | `/api/activity-reports/annotate` | POST | User |
| **Revised exercises (student)** | `/api/revised-exercises/my-revisions` | GET | Student |
| **Revised exercises (student)** | `/api/revised-exercises/view?uid=` | GET | Student or Teacher |

---

## The Development Lens

**Every feature decision should pass through this filter:**

### Questions to ask before building or extending

1. **Which phase does this touch?**
   - Article/Ku (knowledge content) → Phase 1
   - Exercise (assignment/template) → Phase 2
   - Submission processing → Phase 3
   - Feedback generation or display → Phase 4
   - RevisedExercise (targeted revision) → Phase 5
   - Supporting infrastructure (sharing, groups, scheduling) → loop support

2. **Does it strengthen a phase or improve a transition?**
   - Strengthens a phase: Better AI feedback, richer Ku content, cleaner submission UI
   - Improves a transition: Faster Ku→Exercise linking, auto-share on submission, annotation tools

3. **If it touches none of the five phases, why does it exist?**
   - Is it genuinely cross-cutting infrastructure (auth, search, calendar)?
   - Or is it isolated logic that accumulated without serving the loop?
   - Per One Path Forward: isolated logic with no loop connection is a deletion candidate.

### Green flags — features that feed the loop

- Adds a new pathway for feedback to reach the student (Phase 4)
- Improves the quality or speed of submission processing (Phase 3)
- Enriches Ku content with semantic relationships (Phase 1)
- Makes Exercise creation easier for teachers (Phase 2)
- Strengthens the Activity Track (better `ActivityReport` insights)

### Red flags — features to question

- New data model with no `FULFILLS_EXERCISE`, `FEEDBACK_FOR`, or equivalent loop relationship
- A service that reads from multiple domains but writes to none of them (pure read aggregation)
- A UI route that displays data from the loop but adds no new interaction or progression
- Standalone admin tooling with no student-facing outcome

### The Activity Track test

The Activity Track (Tasks/Goals/Habits/Events/Choices/Principles + KU mastery/LP
progress/LS progress → ActivityReport) is as central as the Curriculum Track.
When building Activity Domain or Curriculum features, ask:

- Does this completion data flow into `ProgressReportGenerator`?
- Does this activity pattern become visible in `ActivityReport`?
- Can an admin see this behavior in the activity review snapshot?
- Can the user annotate or reflect on the AI's synthesis of this data?

If the answer to all four is "no", the feature may be accumulating activity data
that never closes the loop.

---

## ProcessorType Taxonomy

`ProcessorType` discriminates who produced a report entity.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md#processortype-taxonomy) for the canonical table.

**Import:** `from core.models.enums.entity_enums import ProcessorType`

---

## Key Source Files

| File | Phase | Purpose |
|------|-------|---------|
| `core/models/ku/ku.py` | 1 | Ku frozen dataclass |
| `core/models/exercises/exercise.py` | 2 | Exercise frozen dataclass |
| `core/models/exercises/revised_exercise.py` | 5 | RevisedExercise frozen dataclass |
| `core/services/revised_exercises/revised_exercise_service.py` | 5 | RevisedExercise CRUD + chain queries |
| `adapters/inbound/revised_exercises_api.py` | 5 | RevisedExercise API routes (teacher + student-facing) |
| `core/ports/curriculum_protocols.py` | 5 | `RevisedExerciseOperations` protocol |
| `core/models/submissions/submission.py` | 3 | Submission base + JOURNAL |
| `core/models/report/submission_report.py` | 4 | SubmissionReport model |
| `core/models/report/activity_report.py` | 4 | ActivityReport model |
| `core/services/submissions/submissions_core_service.py` | 3+4 | CRUD + teacher assessment |
| `core/services/report/submission_report_service.py` | 4 | AI report generation |
| `core/services/report/progress_report_generator.py` | 4 | ActivityReport generation |
| `core/services/report/activity_report_service.py` | 4 | Admin human report; all write paths converge here |
| `core/services/report/teacher_review_service.py` | 4 | Teacher review workflow (review queue, revision, approval) |
| `core/services/background/progress_report_worker.py` | 4 | Scheduled activity report background worker |
| `core/ports/submission_protocols.py` | 3 | Submission protocol interfaces |
| `core/ports/report_protocols.py` | 4 | All report protocols incl. `TeacherReviewOperations`, `ReportRelationshipOperations` |
| `core/ports/group_protocols.py` | support | `GroupOperations` only (group CRUD + membership) |
| `core/services/sharing/unified_sharing_service.py` | 3 | Entity-agnostic sharing |
| `adapters/persistence/neo4j/domain_backends.py` | all | Domain-specific Cypher |
| `adapters/inbound/submissions_ui.py` | 2+3+4 | Student assignments page, submit form, feedback display |
| `adapters/inbound/teaching_ui.py` | 4 | Teacher review queue, feedback form, sidebar dashboard |
| `adapters/inbound/teaching_api.py` | 4 | Teacher API (review queue, revision, approve, dashboard) |
| `ui/patterns/feedback_item.py` | 4 | Shared feedback rendering (used by teaching + submissions UI) |
| `core/prompts/templates/activity_feedback.md` | 4 | LLM prompt template (via PROMPT_REGISTRY) |

---

## Code Walkthrough

### Curriculum Track (artifact-based)

```
1. KuService.create_ku()                           → core/services/ku/ku_core_service.py
   Admin creates a Knowledge Unit
       ↓
2. ExerciseBackend.link_to_curriculum()             → adapters/persistence/neo4j/domain_backends.py
   Teacher links Exercise to Ku via REQUIRES_KNOWLEDGE
       ↓
3. Student submits file
   SubmissionsService.submit_file()                 → core/services/submissions/submissions_core_service.py
   Creates Entity with entity_type='submission', status SUBMITTED→QUEUED→PROCESSING→COMPLETED
       ↓
4. FULFILLS_EXERCISE relationship created
   Auto-sharing: SHARES_WITH (student → teacher)
       ↓
5. TeacherReviewService.get_review_queue()          → core/services/report/teacher_review_service.py
   Teacher sees pending submissions
       ↓
6. TeacherReviewService.submit_report()             → core/services/report/teacher_review_service.py
   Creates SubmissionReport with ProcessorType.HUMAN
   OR SubmissionReportService.generate_report()     → core/services/report/submission_report_service.py
   Creates SubmissionReport with ProcessorType.LLM (via Exercise instructions)
       ↓
7. Student sees feedback, optionally resubmits (revision cycle)
```

### Activity Track (aggregate-based)

```
1. User activity across 6 Activity Domains + 3 Curriculum Domains
   Tasks, Goals, Habits, Events, Choices, Principles + KU mastery, LP progress, LS progress
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

---

## Anti-Patterns

### Don't create a feedback model that inherits Submission when it has no file fields

```python
# WRONG — ActivityReport does not have file uploads
class ActivityReport(Submission):  # No! Submission has file_path, file_size, etc.

# CORRECT — ActivityReport inherits UserOwnedEntity directly
class ActivityReport(UserOwnedEntity):  # No file fields — it's about patterns, not artifacts
```

### Don't put cross-domain Cypher on a single domain backend

```python
# WRONG — ProgressReportGenerator needs Tasks + Goals + Habits + ...
class ReportBackend(UniversalNeo4jBackend):
    async def get_all_activity_completions(self):
        # Can't do this from one domain backend

# CORRECT — cross-domain aggregation uses UserContext.build_rich() (MEGA_QUERY)
class ProgressReportGenerator:
    def __init__(self, context_builder: UserContextBuilder, executor: QueryExecutor, ...):
        # context_builder.build_rich(user_uid, window=...) — MEGA_QUERY with 6-domain
        # activity window CALL{} blocks; entities_rich covers all Activity Domains
        # executor — raw Cypher for annotation lookup only
```

### Don't confuse Exercise scope

```python
# WRONG — PERSONAL exercises don't target groups
exercise = Exercise(scope=ExerciseScope.PERSONAL, group_uid="group_123")  # Nonsense

# CORRECT — scope determines whether group_uid is valid
if exercise.scope == ExerciseScope.ASSIGNED:
    assert exercise.group_uid is not None
```

### Don't let ProcessorType drift

```python
# WRONG — new report source creates a new EntityType
class AdminSummary(UserOwnedEntity):  # New entity for admin-written reports?
    admin_notes: str

# CORRECT — new report sources are new ProcessorType values on existing entities
# ActivityReport with processor_type=HUMAN covers all admin-written activity reports
```

---

## Deep Dive Resources

- [FOUR_PHASED_LEARNING_LOOP.md](/docs/architecture/FOUR_PHASED_LEARNING_LOOP.md) — entry-point overview: two tracks, five phases, how MEGA_QUERY feeds the loop
- [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) — canonical report reference
- [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) — canonical report reference — all services, APIs, graph patterns, ProcessorType taxonomy, Exercise pipeline
- [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)
- [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md)
- [SHARING_PATTERNS.md](/docs/patterns/SHARING_PATTERNS.md)
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)

---

## The System Layers

The learning loop is Layer 1 of a 5-layer system:

```
┌────────────────────────────────────────────┐
│  5. Semantics (coherence)                  │
├────────────────────────────────────────────┤
│  4. Knowledge Graph (structural memory)    │
├────────────────────────────────────────────┤
│  3. Saved Interactions (compounding)       │
├────────────────────────────────────────────┤
│  2. ZPD + UserContext (intelligence)       │
├────────────────────────────────────────────┤
│  1. Learning Loop (base) ◄──── THIS SKILL  │
└────────────────────────────────────────────┘
```

The loop generates graph relationships (Layer 4) as the learner works. ZPD (Layer 2) reads
the graph to assess readiness and generates three action types: **unblock** (blocking gaps),
**learn** (proximal zone), **reinforce** (thin evidence). Saved interactions (Layer 3) —
journals, conversations, annotations — compound the signal quality over time. Each loop
iteration makes the next one smarter.

**See:** [zpd skill](../zpd/SKILL.md), [user-context-intelligence skill](../user-context-intelligence/SKILL.md)

---

## Related Skills

- **[zpd](../zpd/SKILL.md)** — Intelligence layer that makes the loop adaptive (Layer 2)
- **[curriculum-domains](../curriculum-domains/SKILL.md)** — Ku, LS, LP architecture (Phase 1)
- **[activity-domains](../activity-domains/SKILL.md)** — Activity Track entry points (Phase 4 via ActivityReport)
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** — Cross-domain synthesis that feeds ActivityReport
- **[result-pattern](../result-pattern/SKILL.md)** — All services return `Result[T]`
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** — Graph query patterns
- **[pydantic](../pydantic/SKILL.md)** — Request models for submission and feedback routes
- **[prompt-templates](../prompt-templates/SKILL.md)** — `activity_feedback.md` template and PROMPT_REGISTRY
