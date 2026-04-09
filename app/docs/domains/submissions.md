---
title: Submissions + Reports Domain
created: 2025-12-04
updated: 2026-04-03
status: current
category: domains
tags: [submissions, reports, processing-domain, domain]
---

# Submissions + Reports Domain

**Entity Types:** `ExerciseSubmission`, `ExerciseReport`, `ActivityReport`
**UID Prefixes:** `es_` (submissions), `sr_` (exercise reports), `ar_` (activity reports)

## Purpose

The Submissions + Reports domain handles the artifact-based side of SKUEL's Five-Phased Learning Loop. Students submit work (ExerciseSubmission) via two modalities typed by `SubmissionModality`: file upload (`FILE_UPLOAD`) or structured inline form (`STRUCTURED_FORM`). The Exercise's `expected_modality` field determines which path the UI presents. Teachers or AI evaluate submissions (ExerciseReport), and the system generates activity-level reports (ActivityReport) from lived practice across all six Activity Domains.

## Routes

**Authentication:** All API routes require session authentication via `require_authenticated_user(request)`. User-owned routes verify ownership (return 404 for non-owned submissions). No route accepts `user_uid` as a query parameter or form field.

| Route | Type | Purpose |
|-------|------|---------|
| `/study` | UI | Student workspace hub (no sidebar) |
| `/submit` | UI | File upload form |
| `/submissions` | UI | My submitted work |
| `/exercise-reports` | UI | Teacher/AI feedback on exercise submissions |
| `/activity-reports` | UI | AI and scheduled activity reports |
| `/submit-activity-report` | UI | On-demand activity report request |
| `/submissions/{uid}` | UI | Submission detail page |
| `/api/submissions/upload` | API | File upload (session auth) |
| `/api/submissions/form` | API | Structured form submission (session auth) |
| `/api/submissions` | API | List user's submissions (session auth) |
| `/api/submissions/get` | API | Get submission details (ownership-verified) |
| `/api/submissions/content` | API | Get processed content (ownership-verified) |
| `/api/submissions/process` | API | Process submission (ownership-verified) |
| `/api/submissions/download` | API | Download original file (ownership-verified) |
| `/api/submissions/download-processed` | API | Download processed file (ownership-verified) |
| `/api/submissions/statistics` | API | User submission statistics (session auth) |
| `/api/submissions/progress/generate` | API | On-demand progress report generation |
| `/api/submissions/progress` | API | List user's progress reports |
| `/api/submissions/schedule` | API | Schedule CRUD (create, get, update, deactivate) |
| `/api/submissions/assessments` | API | Create assessment (TEACHER role required) |
| `/api/submissions/assessments/given` | API | Teacher's authored assessments |
| `/api/submissions/assessments/received` | API | Student's received assessments |

## Key Files

| Component | Location |
|-----------|----------|
| **Service Package** | `/core/services/submissions/` + `/core/services/report/` |
| Submission Service | `submissions_service.py` (facade) |
| Processing Service | `submissions_processing_service.py` |
| Core Service | `submissions_core_service.py` (delegates assessment to sub-services) |
| Assessment Sub-Service | `assessment_service.py` (teacher assessment CRUD) |
| Search Service | `submissions_search_service.py` (date-bounded reads, text CONTAINS, recency, stats — all filtering in Cypher, entity_type whitelisted to EXERCISE_SUBMISSION) |
| Relationship Service | `submissions_relationship_service.py` |
| Learning Loop Handler | `learning_loop_event_handler_service.py` (event-driven writes: iteration tracking, turnaround calibration, mastery velocity) |
| Learning Loop Query Service | `learning_loop_query_service.py` (read-side peer: queries traversing Interaction/Exercise/Report edges — e.g. submissions-for-path-step) |
| Teacher Review | `teacher_review_service.py` (review queue, report, revision, approval — delegates to `SubmissionsBackend`, `ExerciseBackend`, `GroupBackend`) |
| Exercise Report | `exercise_report_service.py` (AI-generated exercise reports) |
| Activity Report | `activity_report_service.py` (delegates to `ActivityReportBackend`) |
| Progress Generator | `progress_report_generator.py` |
| Schedule Service | `progress_schedule_service.py` |
| Review Queue | `review_queue_service.py` |
| **Models** | `/core/models/submissions/` + `/core/models/report/` |
| ExerciseSubmission | `exercise_submission.py` (frozen dataclass, extends `Submission`) |
| ExerciseReport | `/core/models/report/exercise_report.py` |
| ActivityReport | `/core/models/report/activity_report.py` |
| Report Schedule | `report_schedule.py` (three-tier type system) |
| Request Models | `submission_requests.py`, `report_requests.py` |
| **Routes** | `/adapters/inbound/` |
| Study UI | `study_ui.py` (5-item sidebar) |
| Submissions UI | `submissions_ui.py` |
| Submissions API | `submissions_api.py` |
| Submissions Sharing | `submissions_sharing_api.py` |
| Route Wiring | `submissions_routes.py`, `study_routes.py` |
| **Protocols** | `/core/ports/submission_protocols.py`, `/core/ports/report_protocols.py` |

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `OWNS` | User → Submission | User | Submission ownership |
| `FULFILLS_EXERCISE` | Submission → Exercise (root) | Exercise | Links submission to root exercise; always the original Exercise regardless of revision cycle |
| `FULFILLS_REVISED_EXERCISE` | Submission → RevisedExercise | RevisedExercise | Revision-cycle submissions only; created alongside FULFILLS_EXERCISE |
| `REPORT_FOR` | ExerciseReport → Submission | Submission | Report evaluates submission |
| `APPLIES_KNOWLEDGE` | Submission → Ku | Ku | Knowledge application tracking |
| `SHARES_WITH` | User → RevisedExercise | RevisedExercise | Auto-share revision to student |
| `ASSESSMENT_OF` | Report → User | User | Assessment targets student |
| `HAS_SCHEDULE` | User → ReportSchedule | ReportSchedule | User's generation schedule |

## Progress Report Generation

**On-demand:** `POST /api/submissions/progress/generate` with time_period (7d/14d/30d/90d), depth (summary/standard/detailed), optional domain filter.

**Scheduled:** `ProgressScheduleService` manages recurring schedules (weekly/biweekly/monthly).

## Teacher Assessments

Created via `AssessmentService.create_assessment()` (delegated from `SubmissionsCoreService`, requires TEACHER role). Auto-creates:
- `ASSESSMENT_OF` relationship to student
- `SHARES_WITH` relationship for student access

## Test Coverage

| Service | Test File | Tests | Notes |
|---------|-----------|-------|-------|
| `TeacherReviewService` | `tests/unit/services/test_teacher_review_service.py` | 57 | Access control, review queue, report/revision/approval flows |
| `SubmissionsCoreService` | `tests/unit/services/test_submissions_core_service.py` | 109 | Exercise linking, tags, bulk ops, delete, export |
| `AssessmentService` | `tests/unit/test_assessment_service.py` | 9 | Assessment CRUD |

## See Also

- [Entity Type Architecture](../architecture/ENTITY_TYPE_ARCHITECTURE.md) - Content/Processing section
- [Learning Loop Architecture](../architecture/LEARNING_LOOP_ARCHITECTURE.md) - The core loop
- [Sharing Patterns](../patterns/SHARING_PATTERNS.md) - Three-level visibility
- [ADR-040](../decisions/ADR-040-teacher-exercise-workflow.md) - Teacher exercise workflow
