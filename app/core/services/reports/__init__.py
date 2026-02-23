"""
Ku Service Sub-Services (reports package)
==========================================

"Ku is the heartbeat of SKUEL."

This package contains focused sub-services for the unified Ku domain.
File paths retain the 'reports' name for git history continuity.

Architecture: Content/Processing Domain (not Activity Domain)
- Handles file submission, processing pipelines, content management, and journals
- Different from Activity domains (Tasks, Goals, etc.) which use facade pattern
- Journals are SUBMISSION Ku with journal metadata (merged February 2026)

Sub-services:
- ReportsSubmissionService: File upload and storage
- ReportsProcessingService: Processing orchestration (audio, text, future: PDF, image)
- ReportsCoreService: Content management + journal CRUD
- ReportsSearchService: Query and search operations
- ReportsRelationshipService: Graph relationship creation
- ReportsSharingService: Content sharing between users
- ReportsFeedbackService: AI feedback generation via Exercise
- ReportsScheduleService: Scheduled processing
- ProgressReportGenerator: AI-generated progress reports
"""

from core.services.reports.progress_report_generator import (
    ProgressReportGenerator,
)
from core.services.reports.report_feedback_service import ReportsFeedbackService
from core.services.reports.report_processing_types import (
    ReportsAIInsights,
    ReportsProcessingContext,
)
from core.services.reports.report_schedule_service import (
    ReportsScheduleService,
)
from core.services.reports.report_sharing_service import (
    ReportsSharingService,
)
from core.services.reports.reports_core_service import ReportsCoreService
from core.services.reports.reports_processing_service import (
    ReportsProcessingService,
)
from core.services.reports.reports_relationship_service import (
    ReportsRelationshipService,
)
from core.services.reports.reports_search_service import ReportsSearchService
from core.services.reports.reports_submission_service import (
    ReportsSubmissionService,
)
from core.services.reports.teacher_review_service import TeacherReviewService

__all__ = [
    "ReportsCoreService",
    "ReportsProcessingService",
    "ReportsSearchService",
    "ReportsSubmissionService",
    "ReportsRelationshipService",
    "ReportsSharingService",
    "ReportsFeedbackService",
    "ReportsAIInsights",
    "ReportsProcessingContext",
    "ProgressReportGenerator",
    "ReportsScheduleService",
    "TeacherReviewService",
]
