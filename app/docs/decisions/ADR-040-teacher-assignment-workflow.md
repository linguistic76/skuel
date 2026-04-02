# ADR-040: Teacher Assignment Workflow — Groups, Assignments, and Human Review

**Status:** Accepted
**Date:** 2026-02-06
**Updated:** 2026-02-16 (ReportProject → Assignment rename), 2026-04-02 (admin fallback + auto-enrollment), 2026-04-02 (teacher feedback as .md file upload)
**Author:** Claude Code

## Context

SKUEL needs teachers to assign work to students and review submissions. The pieces exist but aren't unified:

- `ReportType.ASSIGNMENT` — exists, no special workflow
- `ProcessorType.HUMAN` — exists, no implementation
- `MEMBER_OF` relationship — exists in enum, pre-wired in `UserRelationshipService`, no Group nodes
- `Visibility.TEAM` — exists, unused
- `SubmissionsSharingService` — sharing infrastructure works, but only for post-completion manual sharing

Two changes unify these into a coherent architecture:
1. **Group** — new entity for teacher-student class management
2. **Assignment** — instruction template with `scope`, `due_date`, `processor_type` to support teacher assignments

A teacher assignment IS an Assignment with `scope=ASSIGNED`.

## Decision

### 1. Group as First-Class Entity

Groups are the ONE PATH for teacher-student relationships. No direct TEACHES relationship.

```
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
```

Group uses Three-Tier type system (Pattern A): Pydantic request → GroupDTO → Group (frozen dataclass).

### 2. Assignment (Instruction Template)

Assignment provides fields for both personal and teacher-assigned workflows:
- `scope: ExerciseScope` — PERSONAL (default) or ASSIGNED
- `due_date: date | None` — only for ASSIGNED scope
- `processor_type: ProcessorType` — LLM, HUMAN, or HYBRID
- `group_uid: str | None` — target group for ASSIGNED scope

A teacher assignment IS an Assignment with `scope=ASSIGNED`.

### 3. Teacher Review Reuses SHARES_WITH

When a student submits a Ku against an ASSIGNED Assignment:
1. Ku status set to `MANUAL_REVIEW`
2. `SHARES_WITH {role: "teacher"}` auto-created from teacher to submission
3. Teacher's review queue = `get_kus_shared_with_me()` filtered by `role="teacher"` and pending status

### 4. Submission Ownership Stays with Student

Teacher gets access via SHARES_WITH, not ownership transfer.

### 5. UserRelationshipService: :Team → :Group

One Path Forward — `:Team` label replaced with `:Group`. No backward compatibility.

## Graph Schema

```cypher
// New nodes
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})

// Assignment nodes
(:Assignment {uid, user_uid, name, instructions, model, context_notes, domain,
              is_active, scope, due_date, processor_type, group_uid, ...})

// Relationships
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(project:Assignment)-[:FOR_GROUP]->(group:Group)
(submission:Submission)-[:FULFILLS_PROJECT]->(project:Assignment)
(teacher:User)-[:SHARES_WITH {role: "teacher"}]->(submission:Submission)  // Auto on submission
```

## Consequences

### Positive
- Assignment serves both personal and teacher-assigned use cases
- Reuses existing SHARES_WITH infrastructure for teacher access
- Group entity enables future features (team visibility, group analytics, bulk operations)
- Clear ownership model: students own submissions, teachers get shared access

### Negative
- Assignment has 4 fields that are only relevant to ASSIGNED scope
- Group management adds CRUD surface area

## Alternatives Considered

1. **Separate entity for teacher vs personal assignments** — Rejected. One Assignment model with `scope` discriminator follows One Path Forward.
2. **Direct TEACHES relationship** — Rejected. Teacher-student relationship should be mediated by groups for scalability and class management.
3. **Ownership transfer on submission** — Rejected. Student should always own their work. Teacher gets access, not ownership.

## Naming History

Originally implemented as `KuProject` / `ReportProject` in code. Renamed to `Assignment` in February 2026 to align with pipeline vocabulary (Assign → Submit → Analyze → Review). The word "report" was doing triple duty — naming things by their pipeline role eliminates ambiguity.

## Implementation Notes (2026-04-02)

### Admin Fallback for Ownerless Exercises

YAML-ingested exercises have no `(teacher:User)-[:OWNS]->(exercise)` relationship, so
`process_exercise_submission()` found `teacher_uid = None` and returned `NO_TEACHER` —
stalling the entire pipeline. Fixed: `SubmissionsBackend.get_admin_uid()` fetches the
oldest admin user as a fallback teacher. SHARES_WITH is now created for all submissions
regardless of how the exercise was created.

### Auto-Enrollment into Default Group on PathStep Enrollment

`mark_in_progress()` on a PathStep now publishes a `PathStepEnrolled` event.
A handler (`core/events/handlers/path_step_enrollment_handler.py`) subscribes and
auto-enrolls the student in the admin's default group via MERGE — idempotent, silent.
This ensures ASSIGNED exercises with `FOR_GROUP` constraints are accessible to all
enrolled students without requiring explicit group management.

Default group UID pattern: `group_default_{admin_uid}`.
Backend methods: `GroupBackend.get_or_create_default_group()` + `ensure_group_member()`.

### `/teaching/students` Submission-Based (updated 2026-04-02)

`get_students_summary()` sources students from `OWNS exercise_submission` — any student
who has submitted work appears, regardless of PathStep enrollment. An earlier revision
used `IN_PROGRESS PathStep` as the anchor, but that excluded students who submitted
standalone work without enrolling in a curriculum path. The current query also drops the
`OPTIONAL MATCH` two-pass structure: the mandatory `OWNS` match already filters to
submitting students, so `DISTINCT student` + count aggregate in a single pass.

`get_submission_detail_for_teacher()` no longer requires `SHARES_WITH {role:'teacher'}`.
Standalone submissions (no `fulfills_exercise_uid`) skip `exercise_handler.py` entirely —
`auto_share_with_teacher` is never called, so the SHARES_WITH relationship never exists.
Access control for the review detail page is enforced at the route level
(`@require_role(UserRole.TEACHER)`); the Cypher now does a direct lookup by uid.

### Teacher Feedback as Markdown File Upload (2026-04-02)

The review form at `/teaching/review/{uid}` now accepts a `.md` file upload instead of
a plain textarea. This aligns with SKUEL's `.md`-first document format and allows teachers
to write rich, structured feedback in Obsidian or any text editor before submitting.

**How it works:**
- Teacher uploads a `.md` file via the "Submit Feedback" form (multipart/form-data)
- File content → `ExerciseReport.report_content`
- File saved to `data/reports/{teacher_uid}/{submission_uid}/feedback.md`
- File path → `ExerciseReport.report_file_path`
- Students download feedback via `GET /api/reports/{report_uid}/download` (attachment)

**Request Revision** remains text-only — a separate textarea form sends
`RequestRevisionRequest.notes` to `/api/teaching/review/{uid}/revision`.
`SubmitReportRequest` was removed; feedback ingestion is now file-only for HUMAN reports.

## Related

- **ADR-038**: Content Sharing Model (SHARES_WITH infrastructure)
- **Phase 3 (Future)**: Visibility.TEAM implementation, group analytics, bulk operations
