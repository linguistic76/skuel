---
title: Submissions + Feedback Domain
created: 2025-12-04
updated: 2026-02-27
status: current
category: domains
tags: [submissions, feedback, processing-domain, domain]
---

# Submissions + Feedback Domain

**Type:** Content/Processing Domain
**UID Prefix:** `report_`
**Entity Label:** `Report`
**UI Route:** `/reports`

## Purpose

Reports is the primary user-facing interface for all content submissions and system-generated summaries. It encompasses file uploads, journal entries, progress reports, and teacher assessments — all stored as `Report` nodes with `report_type` distinguishing them.

## Report Types

| ReportType | Created By | `is_file_based` | Description |
|------------|-----------|------------------|-------------|
| `TRANSCRIPT` | User upload | Yes | Audio file transcriptions |
| `ASSIGNMENT` | User upload | Yes | Teacher-assigned work with due dates |
| `JOURNAL` | User input | No | Daily reflections |
| `JOURNAL_VOICE` | User upload | Yes | Ephemeral voice journals (max 3, FIFO) |
| `JOURNAL_CURATED` | User input | No | Permanent curated journals |
| `PROGRESS` | System | No | System-generated activity completion summaries |
| `ASSESSMENT` | Teacher | No | Teacher-authored qualitative evaluations of students |

**Content Origin:** User-submitted types (TRANSCRIPT, ASSIGNMENT, JOURNAL, JOURNAL_VOICE, JOURNAL_CURATED) are `ContentOrigin.USER_CREATED`. System-generated types (PROGRESS, ASSESSMENT) are `ContentOrigin.FEEDBACK`. See `EntityType.content_origin()` in `/core/models/enums/entity_enums.py`.

## Routes

| Route | Type | Purpose |
|-------|------|---------|
| `/reports` | UI | Dashboard with 5-item sidebar |
| `/submissions/submit` | UI | File upload form |
| `/submissions/browse` | UI | Browse all reports with type/status filters |
| `/submissions/yours` | UI | User's own reports |
| `/submissions/feedback` | UI | Assessments received from teachers |
| `/submissions/progress` | UI | Generate progress reports + schedule settings |
| `/journals` | UI | Two-tier journal submission (voice + curated) |
| `/api/submissions/upload` | API | File upload endpoint |
| `/api/reports` | API | List reports (supports `report_type` filter) |
| `/api/submissions/progress/generate` | API | On-demand progress report generation |
| `/api/submissions/progress` | API | List user's progress reports |
| `/api/submissions/schedule` | API | Schedule CRUD (create, get, update, deactivate) |
| `/api/submissions/assessments` | API | Create assessment (TEACHER role required) |
| `/api/submissions/assessments/given` | API | Teacher's authored assessments |
| `/api/submissions/assessments/received` | API | Student's received assessments |

## Key Files

| Component | Location |
|-----------|----------|
| **Service Package** | `/core/services/submissions/ + core/services/feedback/` |
| Submission Service | `submissions_service.py` |
| Processing Service | `submissions_processing_service.py` |
| Core Service | `submissions_core_service.py` (includes assessment CRUD) |
| Search Service | `submissions_search_service.py` |
| Relationship Service | `submissions_relationship_service.py` |
| Sharing Service | `report_sharing_service.py` |
| Progress Generator | `progress_report_generator.py` |
| Assignment Service | `assignment_service.py` (Assignment CRUD) |
| Schedule Service | `report_schedule_service.py` |
| Background Worker | `/core/services/background/progress_report_worker.py` |
| **Models** | `/core/models/report/` |
| Report Model | `report.py` (includes `subject_uid` field) |
| Schedule Model | `report_schedule.py` (ReportSchedule three-tier) |
| Request Models | `report_request.py` (4 Pydantic request models) |
| **Routes** | `/adapters/inbound/` |
| Reports UI | `reports_ui.py` (5-item sidebar) |
| Reports API | `reports_api.py` |
| Progress API | `reports_progress_api.py` |
| Assessment API | `reports_assessment_api.py` |
| Route Wiring | `reports_routes.py` (Multi-Factory pattern) |
| Assignments API | `assignments_api.py` |
| Assignments Routes | `assignments_routes.py` |
| Journals UI | `journals_ui.py` |
| **Protocols** | `/core/ports/submission_protocols.py` (4 protocols), `/core/ports/feedback_protocols.py` (3 protocols) |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (`report_` prefix) |
| `user_uid` | `str` | Owner/creator |
| `report_type` | `ReportType` | Type discriminator (7 values) |
| `status` | `ReportStatus` | Processing status |
| `subject_uid` | `str?` | Who the report is about (defaults to `user_uid` for PROGRESS/ASSESSMENT) |
| `title` | `str?` | Report title |
| `processed_content` | `str?` | Generated/processed content (markdown for PROGRESS) |
| `processor_type` | `ProcessorType?` | AUTOMATIC, LLM, HUMAN, HYBRID |
| `metadata` | `dict?` | Type-specific metadata (time_period, stats for PROGRESS) |
| `original_filename` | `str?` | For file-based types only |

## Progress Report Generation

**On-demand:** `POST /api/submissions/progress/generate` with time_period (7d/14d/30d/90d), depth (summary/standard/detailed), optional domain filter.

**Scheduled:** `ReportScheduleService` manages recurring schedules (weekly/biweekly/monthly). `ProgressReportWorker` checks hourly for due schedules.

**Content sections** (depth-controlled):
- Task Completion Summary (completion rate, per-task details)
- Goal Alignment (which goals tasks served)
- Knowledge Application (KUs applied via tasks)
- Habit Activity (active habits, streaks)
- Principle Alignment (choices guided by principles)
- Active Insights (referenced from InsightStore)

## Teacher Assessments

Created via `SubmissionsCoreService.create_assessment()` (requires TEACHER role). Auto-creates:
- `ASSESSMENT_OF` relationship to student
- `SHARES_WITH` relationship for student access

Students see assessments at `/submissions/feedback`.

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `OWNS` | User → Report | User | Report ownership |
| `ASSESSMENT_OF` | Report → User | User | Assessment targets student |
| `SHARES_WITH` | User → Report | Report | Sharing access |
| `HAS_SCHEDULE` | User → ReportSchedule | ReportSchedule | User's generation schedule |
| `FULFILLS_PROJECT` | Ku → Assignment | Assignment | Assignment fulfillment |

## See Also

- [Entity Type Architecture](../architecture/ENTITY_TYPE_ARCHITECTURE.md) - Content/Processing section
- [Sharing Patterns](../patterns/SHARING_PATTERNS.md) - Three-level visibility
- [ADR-040](../decisions/ADR-040-teacher-assignment-workflow.md) - Teacher assignment workflow
- [Protocol Reference](../reference/PROTOCOL_REFERENCE.md) - Submission + Feedback protocols
