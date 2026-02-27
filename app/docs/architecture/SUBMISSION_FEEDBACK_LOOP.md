# Submission / Feedback Loop Architecture

> "The student submits, the system responds, the teacher refines."

## Overview

SKUEL's content processing domain implements a learning loop where **students create**, **AI processes**, and **teachers guide**. Every piece of student work flows through a clear pipeline from raw submission to structured feedback.

## The Four EntityTypes in the Loop

| EntityType | Who Creates | Purpose | ProcessorType |
|--------|------------|---------|---------------|
| `SUBMISSION` | Student uploads file | Raw student work (audio, text, images) | `HUMAN` |
| `JOURNAL` | Admin uploads file | AI-processed reflective writing | `LLM` |
| `AI_REPORT` | System generates | Automated progress summaries | `AUTOMATIC` |
| `FEEDBACK_REPORT` | Teacher **or AI** | Assessment with `subject_uid` pointing to student's Ku | `HUMAN` (teacher) or `LLM` (AI) |

### Naming Rationale

**SUBMISSION** (not "assignment") because:
- "Assignment" in plain English is what a **teacher gives** — that's an `Exercise` with `scope=ASSIGNED`
- "Submission" is what a **student uploads** — file content going through a processing pipeline
- Matches service names: `SubmissionsService`, protocol: `SubmissionOperations`
- Matches existing route language: `/submissions/submit`

### AI Feedback Symmetry

Both teacher feedback and AI feedback produce `FEEDBACK_REPORT` entities — same entity type, different `processor_type`:

| Feedback Source | Service | ProcessorType | Entity Created |
|----------------|---------|---------------|----------------|
| Teacher | `TeacherReviewService.submit_feedback()` | `HUMAN` | `FEEDBACK_REPORT` |
| AI (via Exercise) | `FeedbackService.generate_feedback()` | `LLM` | `FEEDBACK_REPORT` |

Both use atomic Cypher: create entity + `FEEDBACK_FOR` relationship + denormalize to `submission.feedback` in one transaction.

## The Exercise

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

## The Pipeline

```
1. Teacher creates Exercise (scope=ASSIGNED, targets Group)
       |
       v
2. Student submits file → SubmissionsService.submit_file()
       |                   Creates Entity with ku_type=SUBMISSION
       v
3. Processing routes by MIME type (not EntityType):
       audio/* → TranscriptionService → text
       text/*  → Read raw content
       |
       v
4. Ku status: SUBMITTED → QUEUED → PROCESSING → COMPLETED
       |
       v
5. Auto-sharing: FULFILLS_EXERCISE + SHARES_WITH created
       |                             (student → teacher)
       v
6. Teacher reviews in queue → writes FEEDBACK_REPORT
       |                       or requests REVISION
       v
7. Student sees feedback, optionally resubmits
```

## Relationship Graph

```cypher
// The exercise directive
(teacher:User)-[:OWNS]->(exercise:Exercise {scope: "assigned"})
(exercise)-[:FOR_GROUP]->(group:Group)
(student:User)-[:MEMBER_OF]->(group)

// The submission
(student)-[:OWNS]->(submission:Entity {ku_type: "submission"})
(submission)-[:FULFILLS_EXERCISE]->(exercise)

// Sharing for review
(student)-[:SHARES_WITH {role: "teacher"}]->(submission)

// Teacher feedback
(teacher)-[:OWNS]->(feedback:Entity {ku_type: "feedback_report"})
(feedback)-[:FEEDBACK_FOR]->(submission)
```

## Visibility Model

Three-level visibility on every Ku:

| Level | Who Can See | Use Case |
|-------|-------------|----------|
| `PRIVATE` (default) | Owner only | Work in progress |
| `SHARED` | Owner + SHARES_WITH recipients | Teacher review, peer feedback |
| `PUBLIC` | Anyone | Portfolio showcase |

Only `COMPLETED` Ku can be shared (prevents sharing incomplete/failed work).

## Services

| Service | Protocol | Responsibility |
|---------|----------|---------------|
| `SubmissionsService` | `SubmissionOperations` | File upload, storage, submission record creation |
| `SubmissionsProcessingService` | `SubmissionProcessingOperations` | Routes files to processors, manages status transitions |
| `SubmissionsSharingService` | `SubmissionSharingOperations` | Visibility control, SHARES_WITH management |
| `FeedbackService` | `FeedbackOperations` | AI feedback generation → creates `FEEDBACK_REPORT` entity |
| `TeacherReviewService` | `TeacherReviewOperations` | Review queue, human feedback, revision requests, approval |
| `ContentEnrichmentService` | — | Audio transcription + AI formatting |

## UI Surfaces

| Route | Who | What |
|-------|-----|------|
| `/submissions/submit` | Student | Upload files for processing |
| `/submissions/{uid}` | Owner | View submission, sharing controls |
| `/journals/submit` | Admin | Upload files for AI (LLM) processing |
| `/profile/shared` | Any user | "Shared With Me" inbox |
| `/api/teaching/review-queue` | Teacher | Pending review queue |
| `/api/teaching/review/{uid}/feedback` | Teacher | Submit feedback |
| `/api/teaching/review/{uid}/approve` | Teacher | Approve submission |

## See Also

- [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)
- [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md)
- [Sharing Patterns](/docs/patterns/SHARING_PATTERNS.md)
- [14-Domain Architecture](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)
