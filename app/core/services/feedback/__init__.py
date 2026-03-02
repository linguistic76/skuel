"""
Feedback Service Package
=========================

Sub-services for the Feedback stage of SKUEL's educational loop:

    Ku → Exercise → Submission → Feedback
                                      ↑
                          teacher/AI responds to work

Sub-services:
- ActivityReportService: Processor-neutral ActivityReport CRUD (snapshot, submit, history, annotate)
- FeedbackRelationshipService: Level 1 graph queries (no LLM) — pending submissions, summary
- FeedbackService: AI feedback generation via Exercise instructions (Level 2, LLM)
- ReviewQueueService: ReviewRequest queue management (user requests, admin queue)
- TeacherReviewService: Human teacher assessment and review queue
- ProgressFeedbackGenerator: AI-generated progress reports
- ProgressScheduleService: Scheduled processing triggers
"""

from core.services.feedback.activity_report_service import ActivityReportService
from core.services.feedback.feedback_relationship_service import FeedbackRelationshipService
from core.services.feedback.feedback_service import FeedbackService
from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator
from core.services.feedback.progress_schedule_service import ProgressScheduleService
from core.services.feedback.review_queue_service import ReviewQueueService
from core.services.feedback.teacher_review_service import TeacherReviewService

__all__ = [
    "ActivityReportService",
    "FeedbackRelationshipService",
    "FeedbackService",
    "ProgressFeedbackGenerator",
    "ProgressScheduleService",
    "ReviewQueueService",
    "TeacherReviewService",
]
