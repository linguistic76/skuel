"""
Report Service Package
=======================

Sub-services for the Report stage of SKUEL's educational loop:

    Ku → Exercise → Submission → Report
                                    ↑
                        teacher/AI responds to work

Sub-services:
- ActivityReportService: Processor-neutral ActivityReport CRUD (snapshot, submit, history, annotate)
- ReportRelationshipService: Level 1 graph queries (no LLM) — pending submissions, summary
- SubmissionReportService: AI report generation via Exercise instructions (Level 2, LLM)
- ReviewQueueService: ReviewRequest queue management (user requests, admin queue)
- TeacherReviewService: Human teacher assessment and review queue
- ProgressReportGenerator: AI-generated progress reports
- ProgressScheduleService: Scheduled processing triggers
"""

from core.services.report.activity_report_service import ActivityReportService
from core.services.report.progress_report_generator import ProgressReportGenerator
from core.services.report.progress_schedule_service import ProgressScheduleService
from core.services.report.report_relationship_service import ReportRelationshipService
from core.services.report.review_queue_service import ReviewQueueService
from core.services.report.submission_report_service import SubmissionReportService
from core.services.report.teacher_review_service import TeacherReviewService

__all__ = [
    "ActivityReportService",
    "ProgressReportGenerator",
    "ProgressScheduleService",
    "ReportRelationshipService",
    "ReviewQueueService",
    "SubmissionReportService",
    "TeacherReviewService",
]
