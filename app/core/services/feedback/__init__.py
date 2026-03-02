"""
Feedback Service Package
=========================

Sub-services for the Feedback stage of SKUEL's educational loop:

    Ku → Exercise → Submission → Feedback
                                      ↑
                          teacher/AI responds to work

Sub-services:
- ActivityDataReader: Shared query layer for user activity data (one round-trip, two consumers)
- FeedbackRelationshipService: Level 1 graph queries (no LLM) — pending submissions, summary
- FeedbackService: AI feedback generation via Exercise instructions (Level 2, LLM)
- TeacherReviewService: Human teacher assessment and review queue
- ProgressFeedbackGenerator: AI-generated progress reports
- ProgressScheduleService: Scheduled processing triggers
"""

from core.services.feedback.activity_data_reader import ActivityData, ActivityDataReader
from core.services.feedback.feedback_relationship_service import FeedbackRelationshipService
from core.services.feedback.feedback_service import FeedbackService
from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator
from core.services.feedback.progress_schedule_service import ProgressScheduleService
from core.services.feedback.teacher_review_service import TeacherReviewService

__all__ = [
    "ActivityData",
    "ActivityDataReader",
    "FeedbackRelationshipService",
    "FeedbackService",
    "ProgressFeedbackGenerator",
    "ProgressScheduleService",
    "TeacherReviewService",
]
