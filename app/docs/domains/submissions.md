---
title: Submissions + Reports Domain
created: 2025-12-04
updated: 2026-03-22
status: current
category: domains
tags: [submissions, reports, processing-domain, domain]
---

# Submissions + Reports Domain

**Entity Types:** `ExerciseSubmission`, `ExerciseReport`, `ActivityReport`
**UID Prefixes:** `es_` (submissions), `sr_` (exercise reports), `ar_` (activity reports)

## Purpose

The Submissions + Reports domain handles the artifact-based side of SKUEL's Five-Phased Learning Loop. Students upload work (ExerciseSubmission), teachers or AI evaluate it (ExerciseReport), and the system generates activity-level reports (ActivityReport) from lived practice across all six Activity Domains.

## Routes

| Route | Type | Purpose |
|-------|------|---------|
| `/study` | UI | Student workspace hub (no sidebar) |
| `/submit` | UI | File upload form |
| `/submissions` | UI | My submitted work |
| `/exercise-reports` | UI | Teacher/AI feedback on exercise submissions |
| `/activity-reports` | UI | AI and scheduled activity reports |
| `/generate-reports` | UI | On-demand progress report generation |
| `/submissions/{uid}` | UI | Submission detail page |
| `/api/submissions/upload` | API | File upload endpoint |
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
| Search Service | `submissions_search_service.py` |
| Relationship Service | `submissions_relationship_service.py` |
| Learning Loop Handler | `learning_loop_event_handler_service.py` |
| Teacher Review | `teacher_review_service.py` (review queue, report, revision, approval) |
| Submission Report | `submission_report_service.py` (AI-generated exercise reports) |
| Activity Report | `activity_report_service.py` |
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
| `FULFILLS_EXERCISE` | Submission → Exercise | Exercise | Links submission to exercise |
| `REPORT_FOR` | ExerciseReport → Submission | Submission | Report evaluates submission |
| `APPLIES_KNOWLEDGE` | Submission → Ku | Ku | Knowledge application tracking |
| `SHARES_WITH` | User → Submission | Submission | Sharing access (teacher review) |
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
- [Four-Phased Learning Loop](../architecture/FOUR_PHASED_LEARNING_LOOP.md) - The core loop
- [Sharing Patterns](../patterns/SHARING_PATTERNS.md) - Three-level visibility
- [ADR-040](../decisions/ADR-040-teacher-assignment-workflow.md) - Teacher assignment workflow
