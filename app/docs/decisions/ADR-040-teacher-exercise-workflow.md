# ADR-040: Teacher Exercise Workflow — Groups, Exercises, and Human Review

> **2026-04-14 — Partially superseded by [ADR-053](ADR-053-groups-first-class-and-unified-sharing.md).** The `FOR_GROUP` edge described in this ADR has been retired. Curriculum (Exercise, PathStep, LearningPath) is now shared to groups via `SHARED_WITH_GROUP` through `UnifiedSharingService`. The rest of the workflow — teacher review, submissions, OWNS-based review queue — remains current.
>
> **2026-04-14 — Partially superseded by [ADR-054](ADR-054-user-entry-unified-submissions.md).** `ExerciseSubmission` has been collapsed into `UserEntry`. The OWNS-based review queue is replaced by a symmetric `SHARED_WITH_GROUP` + `pipeline='teacher_review'` graph pattern. The learning loop (Exercise → Submission → Report → RevisedExercise) is preserved as emergent relationships rather than a type hierarchy.

**Status:** Accepted
**Date:** 2026-02-06
**Updated:** 2026-02-16 (ReportProject → Assignment rename), 2026-04-02 (admin fallback + auto-enrollment), 2026-04-02 (teacher feedback as .md file upload), 2026-04-02 (fix status guards for submit_report + request_revision), 2026-04-02 (review queue + dashboard stats switch to OWNS-based approach), 2026-04-03 (Assignment → Exercise rename throughout)
**Author:** Claude Code

## Context

SKUEL needs teachers to assign work to students and review submissions. The pieces exist but aren't unified:

- `ReportType.ASSIGNMENT` — exists, no special workflow
- ProcessorType.HUMAN — exists, no implementation
- `MEMBER_OF` relationship — exists in enum, pre-wired in `UserRelationshipService`, no Group nodes
- `Visibility.TEAM` — exists, unused
- SubmissionsSharingService — sharing infrastructure works, but only for post-completion manual sharing

Two changes unify these into a coherent architecture:
1. **Group** — new entity for teacher-student class management
2. **Exercise** — instruction template with `scope`, `due_date`, `processor_type` to support teacher exercises

A teacher exercise IS an Exercise with `scope=ASSIGNED`.

## Decision

### 1. Group as First-Class Entity

Groups are the ONE PATH for teacher-student relationships. No direct TEACHES relationship.

```
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
```

Group uses Three-Tier type system (Pattern A): Pydantic request → GroupDTO → Group (frozen dataclass).

### 2. Exercise (Instruction Template)

Exercise provides fields for both personal and teacher-assigned workflows:
- `scope: ExerciseScope` — PERSONAL (default) or ASSIGNED
- `due_date: date | None` — only for ASSIGNED scope
- ~~processor_type: ProcessorType — LLM, HUMAN, or HYBRID~~ — **never implemented; withdrawn 2026-07-28**
- `group_uid: str | None` — target group for ASSIGNED scope

> **Amendment (2026-07-28): the `processor_type` clause is withdrawn.**
> It was never implemented on `Exercise` — the entity has no such field, and the
> ProcessorType enum it named no longer exists (ADR-054 split it into
> `Pipeline` + `ReportSource`; `scripts/health/stale_names.py` already flags the
> name as stale). The only surviving fragment was
> `ExerciseCreateRequest.processor_type`, a Pydantic field that
> `ConversionServiceV2.create_to_pure` silently discarded because it filters to
> the target dataclass's field names before construction — so the API accepted
> and documented a knob that did nothing. That field is now deleted.
>
> Processor/source discrimination is a **Report** concern, not an Exercise one:
> `EntryReport.processor_type` / `ActivityReport.processor_type` carry
> `ReportSource` (HUMAN / LLM / AUTOMATIC) and are live. See ADR-054.

A teacher exercise IS an Exercise with `scope=ASSIGNED`.

### 3. Teacher Review — OWNS-Based Discovery (updated 2026-04-03)

When a student submits against an ASSIGNED Exercise:
1. Submission status set to `SUBMITTED`
2. `FULFILLS_EXERCISE` relationship created (submission → root Exercise)
3. Teacher's review queue = `get_review_queue()` — discovers all student exercise_submissions via `OWNS`

No `SHARES_WITH` relationship is created between teacher and submission.
`verify_teacher_authority(teacher_uid, student_uid)` checks that the teacher has an explicit group oversight relationship over the student (i.e. `(teacher)-[:OWNS]->(:Group)<-[:MEMBER_OF]-(student)`). Access is role-gated (`TEACHER` role required at route level).

### 4. Submission Ownership Stays with Student

Student always owns the submission. Teacher discovers it via the review queue (OWNS-based).

### 5. UserRelationshipService: :Team → :Group

One Path Forward — `:Team` label replaced with `:Group`. No backward compatibility.

## Graph Schema

```cypher
// New nodes
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})

// Exercise nodes
(:Exercise {uid, user_uid, name, instructions, model, context_notes, domain,
            is_active, scope, due_date, processor_type, group_uid, ...})

// Relationships
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(submission:Submission)-[:FULFILLS_EXERCISE]->(exercise:Exercise)
```

## Consequences

### Positive
- Exercise serves both personal and teacher-assigned use cases
- Review queue uses OWNS-based discovery — catches all submissions regardless of exercise origin
- Group entity enables future features (team visibility, group analytics, bulk operations)
- Clear ownership model: students own submissions, teachers discover via role-gated queue

### Negative
- Exercise has 4 fields that are only relevant to ASSIGNED scope
- Group management adds CRUD surface area

## Alternatives Considered

1. **Separate entity for teacher vs personal exercises** — Rejected. One Exercise model with `scope` discriminator follows One Path Forward.
2. **Direct TEACHES relationship** — Rejected. Teacher-student relationship should be mediated by groups for scalability and class management.
3. **Ownership transfer on submission** — Rejected. Student should always own their work. Teacher gets access, not ownership.

## Naming History

Originally implemented as `KuProject` / `ReportProject` in code. Renamed to `Assignment` in February 2026 to align with pipeline vocabulary (Assign → Submit → Analyze → Review). Renamed again to `Exercise` in March 2026 — "Exercise" accurately describes the entity's role as an instruction template for student work (personal, assigned, or assessment).

## Implementation Notes (2026-04-02)

### Admin Fallback for Ownerless Exercises

YAML-ingested exercises have no `(teacher:User)-[:OWNS]->(exercise)` relationship.
`process_exercise_submission()` validates scope and group membership but does not
require a teacher OWNS relationship — the review queue discovers submissions via
the student's OWNS relationship, not teacher sharing.

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

`get_submission_detail_for_teacher()` does a direct lookup by submission UID — no
`SHARES_WITH` gate. Access control is enforced at the route level
(`@require_role(UserRole.TEACHER)`); the Cypher does a direct lookup by uid.

### Review Queue + Dashboard Stats — OWNS-Based (2026-04-02)

`get_review_queue()` and `get_dashboard_stats()` previously anchored on
`(teacher)-[:SHARES_WITH {role:'teacher'}]->(submission)`. This returned 0 results for
submissions from YAML-ingested exercises and any path where `auto_share_with_teacher()`
was skipped. Both methods now use the same OWNS anchor as `get_students_summary()`:

```cypher
MATCH (student:User)-[:OWNS]->(sub:Entity {entity_type: 'exercise_submission'})
WHERE student.uid <> $teacher_uid
```

Default status filter: `submitted` + `active` (pending work only). `revision_requested`
is a distinct state visible in the student detail Revision Requested sidebar section — not counted
as pending. `verify_teacher_authority()` evaluates the teacher's active group governance over the student via Neo4j.

### Teacher Review Status Guards (2026-04-02)

`TeacherReviewService` enforces Cypher-level status guards for all three review actions:

| Action | Method | Sets Submission To | Requires Submission In |
|--------|--------|--------------------|------------------------|
| Submit feedback | `submit_report()` | `COMPLETED` | `SUBMITTED`, `ACTIVE` |
| Request revision | `request_revision()` | `REVISION_REQUESTED` | `SUBMITTED`, `ACTIVE` |
| Approve | `approve_report()` | `COMPLETED` | `REVISION_REQUESTED` |

- `SUBMITTED` — newly submitted by student (initial submission)
- `ACTIVE` — resubmitted after a revision cycle

Both `submit_report` and `request_revision` accept either status because the teacher
sees the same review page regardless of which cycle the submission is in.

The three HTMX-targeted routes (`/api/teaching/review/{uid}/report`,
`/api/teaching/review/{uid}/revision`, `/api/teaching/review/{uid}/approve`) return
FastHTML FT components (not JSON) so HTMX can inject inline success/error banners
into the `#review-result` div.

### Teacher Feedback as Markdown File Upload (2026-04-02)

The review form at `/teaching/review/{uid}` now accepts a `.md` file upload instead of
a plain textarea. This aligns with SKUEL's `.md`-first document format and allows teachers
to write rich, structured feedback in Obsidian or any text editor before submitting.

**How it works:**
- Teacher uploads a `.md` file via the "Submit Feedback" form (multipart/form-data)
- File content → `ExerciseReport.content` (inherited from Entity)
- File saved to `data/reports/{teacher_uid}/{submission_uid}/feedback.md`
- File path → `ExerciseReport.report_file_path`
- Students download feedback via `GET /api/reports/{report_uid}/download` (attachment)

**Request Revision** remains text-only — a separate textarea form sends
`RequestRevisionRequest.notes` to `/api/teaching/review/{uid}/revision`.
`SubmitReportRequest` was removed; feedback ingestion is now file-only for HUMAN reports.

### CLI-Based Offline Review Workflow (2026-04-02)

Teachers can export their entire review queue to local markdown files, review and
annotate offline (in Obsidian or any text editor), then import the reports back in
a single batch — bypassing the web UI entirely.

**Two scripts in `scripts/`:**

```bash
# Export pending submissions → ~/skuel-reviews/pending/<uid>.md
uv run scripts/export_submissions.py --teacher-uid <uid>

# Import written reports → posts ExerciseReports, moves files to imported/
uv run scripts/import_reports.py --teacher-uid <uid>
```

**Report file format** (`~/skuel-reviews/done/<uid>.md`):
```markdown
---
submission_uid: es_abc123
action: report        # report (default) | revision | approve
---

Your feedback here as markdown...
```

Both scripts use the same `TeacherReviewService` methods as the web UI
(`submit_report`, `request_revision`, `approve_report`). The `pending/` export
files are read-only — teachers write reports as separate files in `done/`.

**Pending-State Reconciliation:**
To prevent feedback from being silently lost if a teacher writes a report in `done/<uid>.md` but forgets to run the import script (or if an import fails), a reconciliation mechanism is built-in:
1. `export_submissions.py` writes an `export_manifest.json` containing the UIDs of all exported submissions.
2. `import_reports.py` validates this manifest after importing. Any file from the manifest that has not been successfully imported is explicitly flagged in the terminal.

**Design Evolution & Open Questions:**
While this effectively solves the offline-first "silent loss" problem, there are open questions about the strength of the design and its future evolution:
- **Manifest State Management**: The current `export_manifest.json` is local and overwritten on every export. What happens in multi-device workflows where a teacher exports on a desktop but imports on a laptop?
- **Two-Way Sync**: Is a one-directional manifest sufficient, or should the CLI evolve towards a robust bidirectional state-sync (perhaps maintaining an internal SQLite cache or leveraging Git-like content addressability)?
- **Automated Workflow**: Should the reliance on a distinct `import_reports.py` execution be eliminated entirely via a background directory watcher (e.g. `watchdog`) that imports files the moment they are saved to `done/`?
- **In-Band Error Reporting**: Currently, errors during import (like invalid frontmatter) are logged to the terminal. Could the system automatically append an `ERROR` banner to the Markdown file itself to notify the teacher directly in Obsidian?
- **Multi-Teacher Conflicts**: Does the manifest appropriately handle scenarios where another teacher approves the submission via the web UI while it sits locally in `pending/`?

## Related

- **ADR-038**: Content Sharing Model (SHARES_WITH infrastructure)
- **Phase 3 (Future)**: Visibility.TEAM implementation, group analytics, bulk operations
