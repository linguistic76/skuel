# Submission / Feedback Loop Architecture

> "The student submits, the system responds, the teacher refines."

## Overview

SKUEL's content processing domain implements a learning loop where **students create**, **AI processes**, and **teachers guide**. Every piece of student work flows through a clear pipeline from raw submission to structured feedback.

## The Four KuTypes in the Loop

| KuType | Who Creates | Purpose | ProcessorType |
|--------|------------|---------|---------------|
| `SUBMISSION` | Student uploads file | Raw student work (audio, text, images) | `HUMAN` |
| `JOURNAL` | Admin uploads file | AI-processed reflective writing | `LLM` |
| `AI_REPORT` | System generates | Automated progress summaries | `AUTOMATIC` |
| `FEEDBACK_REPORT` | Teacher writes | Assessment with `subject_uid` pointing to student's Ku | `HUMAN` |

### Naming Rationale

**SUBMISSION** (not "assignment") because:
- "Assignment" in plain English is what a **teacher gives** — that's `Assignment` with `scope=ASSIGNED`
- "Submission" is what a **student uploads** — file content going through a processing pipeline
- Matches existing service names: `KuSubmissionService`, `KuSubmissionOperations`
- Matches existing route language: `/reports/submit`

## The Assignment

An `Assignment` is the teacher's directive — instructions for what students should produce.

```
Assignment (scope=ASSIGNED)
    |
    +-- instructions: str        # What to do
    +-- due_date: date           # When it's due
    +-- group_uid: str           # Which class
    +-- processor_type: str      # How to process submissions
```

**Two scopes:**
- `PERSONAL` — User's own AI template for journal processing
- `ASSIGNED` — Teacher-created directive targeting a Group

## The Pipeline

```
1. Teacher creates Assignment (scope=ASSIGNED, targets Group)
       |
       v
2. Student submits file → KuSubmissionService.submit_file()
       |                   Creates Ku with ku_type=SUBMISSION
       v
3. Processing routes by MIME type (not KuType):
       audio/* → TranscriptionService → text
       text/*  → Read raw content
       |
       v
4. Ku status: SUBMITTED → QUEUED → PROCESSING → COMPLETED
       |
       v
5. Auto-sharing: FULFILLS_PROJECT + SHARES_WITH created
       |                            (student → teacher)
       v
6. Teacher reviews in queue → writes FEEDBACK_REPORT
       |                       or requests REVISION
       v
7. Student sees feedback, optionally resubmits
```

## Relationship Graph

```cypher
// The assignment directive
(teacher:User)-[:OWNS]->(project:Assignment {scope: "assigned"})
(project)-[:FOR_GROUP]->(group:Group)
(student:User)-[:MEMBER_OF]->(group)

// The submission
(student)-[:OWNS]->(submission:Ku {ku_type: "submission"})
(submission)-[:FULFILLS_PROJECT]->(project)

// Sharing for review
(student)-[:SHARES_WITH {role: "teacher"}]->(submission)

// Teacher feedback
(teacher)-[:OWNS]->(feedback:Ku {ku_type: "feedback_report"})
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

| Service | Responsibility |
|---------|---------------|
| `KuSubmissionService` | File upload, storage, Ku record creation |
| `KuProcessingService` | Routes files to processors, manages status transitions |
| `KuSharingService` | Visibility control, SHARES_WITH management |
| `TeacherReviewService` | Review queue, feedback, revision requests, approval |
| `TranscriptProcessorService` | Audio transcription + AI formatting |

## UI Surfaces

| Route | Who | What |
|-------|-----|------|
| `/reports/submit` | Student | Upload files for processing |
| `/reports/{uid}` | Owner | View submission, sharing controls |
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
