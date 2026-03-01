---
name: learning-loop
description: >
  Expert guide for SKUEL's Four-Phased Learning Loop — the core purpose of the app.
  Use when building or reviewing any feature involving Ku, Exercise, Submission, or Feedback.
  TRIGGER when: working on submissions, exercises, feedback generation, activity reports,
  teacher review, AI assessment, or when designing a new feature and asking "where does this fit?".
  This skill provides the development lens: every new feature must either strengthen a loop phase
  or improve the transition between phases. Features that serve no loop purpose are candidates
  for deletion per SKUEL's One Path Forward philosophy.
allowed-tools: Read, Grep, Glob
---

# The Four-Phased Learning Loop

> "Knowledge is learned by doing, evaluated by responding, and refined by reflecting."

The Four-Phased Learning Loop is the **core purpose of SKUEL**. Every feature in the
codebase either feeds this loop, supports its infrastructure, or should be questioned.
Understanding the loop is the prerequisite for all architectural decisions.

---

## The Loop at a Glance

```
╔══════════════════════════════════════════════════════════════╗
║              FOUR-PHASED LEARNING LOOP                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  CURRICULUM TRACK (artifact-based)                           ║
║  ─────────────────────────────────────────────────────────   ║
║  [Ku] ──→ [Exercise] ──→ [Submission/Journal] ──→ [Feedback] ║
║   ↑             ↓              ↓                      ↓      ║
║  admin       teacher        student               teacher/AI  ║
║  creates     assigns        uploads              assesses     ║
║                                                              ║
║  ACTIVITY TRACK (aggregate-based)                            ║
║  ─────────────────────────────────────────────────────────   ║
║  [Tasks + Goals + Habits + Events + Choices + Principles]    ║
║                    ↓ (over time window)                      ║
║             [Activity Report] ←── AI or Admin               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**Two tracks, one loop.** Activity Domains are equal entry points — a user's lived
practice (Tasks, Goals, Habits) receives the same feedback infrastructure as curriculum
work. The mechanism differs (`ACTIVITY_REPORT` vs `SUBMISSION_FEEDBACK`), but both
close the loop: student does work, system or teacher responds.

---

## Phase 1: Ku — The Knowledge Unit

**What it is:** Atomic curriculum content. A single "brick" of knowledge, admin-created
and shared across all users. The curriculum track begins here.

**EntityType:** `EntityType.KU`
**Model:** `core/models/curriculum/ku.py` — `Ku(Curriculum)` frozen dataclass
**DTO:** `core/models/curriculum/ku_dto.py`
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
**Model:** `core/models/curriculum/exercise.py` — `Exercise(Curriculum)` frozen dataclass
**DTO:** `core/models/curriculum/exercise_dto.py`
**Neo4j label:** `:Entity:Exercise`

**Key fields:**
```python
instructions: str                 # Teacher's directive — ALSO used as LLM prompt
model: str                        # LLM to use: "claude-3-5-sonnet-20241022"
scope: ExerciseScope              # PERSONAL (self-directed) | ASSIGNED (classroom)
due_date: date | None             # ASSIGNED only — when submission is due
group_uid: str | None             # ASSIGNED only — which class receives this
enrichment_mode: str | None       # Processing strategy for the submission
context_notes: tuple[str, ...]    # Reference materials (immutable)
```

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
```

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(exercise:Entity:Exercise {
    scope: 'assigned',
    instructions: '...',         // This IS the LLM prompt for feedback generation
    model: 'claude-3-5-sonnet-20241022',
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

**EntityTypes:** `EntityType.SUBMISSION` and `EntityType.JOURNAL`
**Model:** `core/models/submissions/submission.py` — `Submission(UserOwnedEntity)` frozen dataclass
**DTO:** `core/models/submissions/submission_dto.py`
**Neo4j label:** `:Entity:Submission` or `:Entity:Journal`

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

**Processing pipeline:**
```
Student uploads file
        ↓
SubmissionsService.submit_file() → Entity with status: SUBMITTED
        ↓
Route by MIME type:
  audio/* → TranscriptionService → processed_content (text)
  text/*  → Read raw content
        ↓
Status: PROCESSING → COMPLETED
        ↓
Auto-create relationships:
  FULFILLS_EXERCISE (if linked to exercise)
  SHARES_WITH {role: 'teacher'} (if ASSIGNED exercise → teacher gets access)
```

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

## Phase 4: Feedback — The Response

**What it is:** The evaluation. Two structurally distinct entities cover two distinct
entry points. Both close the loop — both say "here is what your work means."

### 4a. SUBMISSION_FEEDBACK — Response to an Artifact

**EntityType:** `EntityType.SUBMISSION_FEEDBACK`
**Model:** `core/models/feedback/submission_feedback.py` — `SubmissionFeedback(Submission)` frozen dataclass
**Neo4j label:** `:Entity:SubmissionFeedback`
**Inherits:** Full `Submission` model (+2 feedback-specific fields)

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
| AI | `FeedbackService.generate_feedback()` | `LLM` | Exercise has `instructions` |

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(feedback:Entity:SubmissionFeedback {
    subject_uid: 'submission_uid_being_evaluated',
    processor_type: 'human',     // or 'llm'
    feedback: 'Your analysis shows...'
})
(feedback)-[:FEEDBACK_FOR]->(submission:Entity:Submission)
```

**Structural position:** Leaf domain. One submission in, one feedback node out.
Fits the standard 4-layer pattern: `FeedbackOperations` protocol → `SubmissionsBackend`
→ `FeedbackService` / `SubmissionsCoreService` → sub-services.

---

### 4b. ACTIVITY_REPORT — Response to Activity Patterns

**EntityType:** `EntityType.ACTIVITY_REPORT`
**Model:** `core/models/feedback/activity_report.py` — `ActivityReport(UserOwnedEntity)` frozen dataclass
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
| Scheduled system | `ProgressFeedbackWorker` → `ProgressFeedbackGenerator` | `AUTOMATIC` | Cron schedule |
| On-demand AI | `ProgressFeedbackGenerator.generate()` | `LLM` | User requests via API |
| Admin writes | `ActivityReviewService.submit_activity_feedback()` | `HUMAN` | Admin reviews snapshot |

**Structural position:** Cross-domain aggregator. Cannot fit the leaf domain model
because it reads across all 6 Activity Domain backends. `ProgressFeedbackGenerator`
accepts a `QueryExecutor` rather than a single domain backend — this is intentional.
Per SKUEL's architecture rule: domain-specific Cypher on domain backends; cross-domain
aggregation stays in services. `ProgressFeedbackGenerator` IS the cross-domain service.

**LLM generation flow:**
```
1. Query completions across Tasks, Goals, Habits, Choices (time window)
2. Cross-reference active Insights
3. Send stats as JSON context to LLM via activity_feedback.md prompt template
4. LLM returns qualitative analysis with patterns, trends, recommendations
5. Create ActivityReport with processed_content = LLM output
6. Graceful fallback: if LLM fails → ProcessorType.AUTOMATIC + programmatic markdown
```

**Prompt template:** `core/services/feedback/prompts/activity_feedback.md`

---

## The Binding Graph Relationships

| Relationship | Connects | Purpose |
|---|---|---|
| `REQUIRES_KNOWLEDGE` | `Exercise` → `Ku` | Exercise is grounded in this knowledge |
| `FOR_GROUP` | `Exercise` → `Group` | ASSIGNED exercise targets this classroom |
| `FULFILLS_EXERCISE` | `Submission` → `Exercise` | Student's work satisfies this exercise |
| `SHARES_WITH` | `Submission` → `User` | Auto-share to teacher for ASSIGNED exercises |
| `FEEDBACK_FOR` | `SubmissionFeedback` → `Submission` | Feedback evaluates this specific artifact |

**RelationshipName enum locations:**
```python
from core.models.enums.relationship_names import RelationshipName

RelationshipName.REQUIRES_KNOWLEDGE   # Exercise → Ku
RelationshipName.FOR_GROUP            # Exercise → Group
RelationshipName.FULFILLS_EXERCISE    # Submission → Exercise
RelationshipName.SHARES_WITH          # Submission → User (also group sharing)
RelationshipName.FEEDBACK_FOR         # SubmissionFeedback → Submission
RelationshipName.SHARED_WITH_GROUP    # Submission → Group (group sharing)
```

---

## Service Architecture Summary

| Phase | Service | Protocol | Backend | Key Methods |
|-------|---------|----------|---------|-------------|
| **Ku** | `KuService` | `KuOperations` | `KuBackend` | `organize`, `get_subkus`, CRUD |
| **Exercise** | `ExerciseService` | `ExerciseOperations` | `ExerciseBackend` | `link_to_curriculum`, CRUD |
| **Submission** | `SubmissionsService` | `SubmissionOperations` | `SubmissionsBackend` | `submit_file`, `check_access`, share methods |
| **Submission processing** | `SubmissionsProcessingService` | `SubmissionProcessingOperations` | `SubmissionsBackend` | Processing pipeline |
| **Submission feedback** | `FeedbackService` + `SubmissionsCoreService` | `FeedbackOperations` | `SubmissionsBackend` | `generate_feedback`, `create_assessment` |
| **Activity Report (auto/LLM)** | `ProgressFeedbackGenerator` | `ProgressFeedbackOperations` | `QueryExecutor` (cross-domain) | `generate`, `create_scheduled` |
| **Activity Report (human)** | `ActivityReviewService` | `ActivityReviewOperations` | `QueryExecutor` | `create_activity_snapshot`, `submit_activity_feedback` |

**Protocols location:** `core/ports/feedback_protocols.py`, `core/ports/submission_protocols.py`

---

## API Routes Per Phase

| Phase | Route | Method | Who |
|-------|-------|--------|-----|
| **Submission** | `/submissions/submit` | POST | Student |
| **Submission** | `/submissions/{uid}` | GET | Student (owner) |
| **Submission** | `/api/submissions/...` | GET/POST | Student |
| **Submission sharing** | `/api/share/group` | POST | Student |
| **Submission sharing** | `/api/submissions/shared-with-me` | GET | Teacher |
| **Submission feedback** | `/api/feedback/assessments` | POST | Teacher |
| **Submission feedback** | `/api/feedback/assessments/for-student` | GET | Teacher |
| **Teacher review** | `/api/teaching/review-queue` | GET | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/feedback` | POST | Teacher |
| **Activity report** | `/api/feedback/progress/generate` | POST | User |
| **Activity report** | `/api/feedback/progress` | GET | User |
| **Activity report** | `/api/feedback/schedule` | POST | User |
| **Activity review (admin)** | `/api/activity-review/snapshot` | GET | Admin |
| **Activity review (admin)** | `/api/activity-review/submit` | POST | Admin |
| **Activity review (admin)** | `/api/activity-review/queue` | GET | Admin |
| **Activity review (user)** | `/api/activity-review/history` | GET | User |
| **Annotation** | `/api/activity-reports/annotate` | POST | User |

---

## The Development Lens

**Every feature decision should pass through this filter:**

### Questions to ask before building or extending

1. **Which phase does this touch?**
   - Ku (knowledge content) → Phase 1
   - Exercise (assignment/template) → Phase 2
   - Submission processing → Phase 3
   - Feedback generation or display → Phase 4
   - Supporting infrastructure (sharing, groups, scheduling) → loop support

2. **Does it strengthen a phase or improve a transition?**
   - Strengthens a phase: Better AI feedback, richer Ku content, cleaner submission UI
   - Improves a transition: Faster Ku→Exercise linking, auto-share on submission, annotation tools

3. **If it touches none of the four phases, why does it exist?**
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

The Activity Track (Tasks/Goals/Habits → ActivityReport) is as central as the
Curriculum Track. When building Activity Domain features, ask:

- Does this completion data flow into `ProgressFeedbackGenerator`?
- Does this activity pattern become visible in `ActivityReport`?
- Can an admin see this behavior in the activity review snapshot?
- Can the user annotate or reflect on the AI's synthesis of this data?

If the answer to all four is "no", the feature may be accumulating activity data
that never closes the loop.

---

## ProcessorType Taxonomy

`ProcessorType` discriminates who produced a feedback entity:

| ProcessorType | Who | Applies to |
|---|---|---|
| `HUMAN` | Teacher writes | `SUBMISSION_FEEDBACK` (teacher assessment) |
| `HUMAN` | Admin writes | `ACTIVITY_REPORT` (activity review) |
| `LLM` | AI via Exercise instructions | `SUBMISSION_FEEDBACK` (AI assessment) |
| `LLM` | AI on demand | `ACTIVITY_REPORT` (activity summary) |
| `AUTOMATIC` | Scheduled system | `ACTIVITY_REPORT` (periodic progress report) |

**Import:** `from core.models.enums.entity_enums import ProcessorType`

---

## Key Source Files

| File | Phase | Purpose |
|------|-------|---------|
| `core/models/curriculum/ku.py` | 1 | Ku frozen dataclass |
| `core/models/curriculum/exercise.py` | 2 | Exercise frozen dataclass |
| `core/models/submissions/submission.py` | 3 | Submission base + JOURNAL |
| `core/models/feedback/submission_feedback.py` | 4 | SubmissionFeedback model |
| `core/models/feedback/activity_report.py` | 4 | ActivityReport model |
| `core/services/submissions/submissions_core_service.py` | 3+4 | CRUD + teacher assessment |
| `core/services/feedback/feedback_service.py` | 4 | AI feedback generation |
| `core/services/feedback/progress_feedback_generator.py` | 4 | ActivityReport generation |
| `core/services/feedback/activity_review_service.py` | 4 | Admin human feedback |
| `core/ports/submission_protocols.py` | 3 | Submission protocol interfaces |
| `core/ports/feedback_protocols.py` | 4 | Feedback protocol interfaces |
| `core/services/sharing/unified_sharing_service.py` | 3 | Entity-agnostic sharing |
| `adapters/persistence/neo4j/domain_backends.py` | all | Domain-specific Cypher |
| `core/services/feedback/prompts/activity_feedback.md` | 4 | LLM prompt template |

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
# WRONG — ProgressFeedbackGenerator needs Tasks + Goals + Habits + ...
class FeedbackBackend(UniversalNeo4jBackend):
    async def get_all_activity_completions(self):
        # Can't do this from one domain backend

# CORRECT — cross-domain aggregation stays in the service via QueryExecutor
class ProgressFeedbackGenerator:
    def __init__(self, executor: QueryExecutor, ...):
        # executor gives raw Cypher access across all domains
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
# WRONG — new feedback source creates a new EntityType
class AdminSummary(UserOwnedEntity):  # New entity for admin-written feedback?
    admin_notes: str

# CORRECT — new feedback sources are new ProcessorType values on existing entities
# ActivityReport with processor_type=HUMAN covers all admin-written activity feedback
```

---

## Deep Dive Resources

- [FEEDBACK_ARCHITECTURE.md](/docs/architecture/FEEDBACK_ARCHITECTURE.md) — canonical feedback reference
- [SUBMISSION_FEEDBACK_LOOP.md](/docs/architecture/SUBMISSION_FEEDBACK_LOOP.md) — pipeline diagram
- [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)
- [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md)
- [SHARING_PATTERNS.md](/docs/patterns/SHARING_PATTERNS.md)
- [FOURTEEN_DOMAIN_ARCHITECTURE.md](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)

---

## Related Skills

- **[curriculum-domains](../curriculum-domains/SKILL.md)** — Ku, LS, LP architecture (Phase 1)
- **[activity-domains](../activity-domains/SKILL.md)** — Activity Track entry points (Phase 4 via ActivityReport)
- **[result-pattern](../result-pattern/SKILL.md)** — All services return `Result[T]`
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** — Graph query patterns
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** — Cross-domain synthesis that feeds ActivityReport
- **[pydantic](../pydantic/SKILL.md)** — Request models for submission and feedback routes
