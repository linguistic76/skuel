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
- KuSubmissionService: File upload and storage
- KuProcessingService: Processing orchestration (audio, text, future: PDF, image)
- KuCoreService: Content management + journal CRUD
- KuSearchService: Query and search operations
- KuRelationshipService: Graph relationship creation
- KuSharingService: Content sharing between users
- KuFeedbackService: AI feedback generation via Exercise
- KuScheduleService: Scheduled processing
- ProgressKuGenerator: AI-generated progress reports
"""

from core.services.reports.progress_report_generator import (
    ProgressKuGenerator,
)
from core.services.reports.report_feedback_service import KuFeedbackService
from core.services.reports.report_processing_types import (
    KuAIInsights,
    KuProcessingContext,
)
from core.services.reports.report_schedule_service import (
    KuScheduleService,
)
from core.services.reports.report_sharing_service import (
    KuSharingService,
)
from core.services.reports.reports_core_service import KuCoreService
from core.services.reports.reports_processing_service import (
    KuProcessingService,
)
from core.services.reports.reports_relationship_service import (
    KuRelationshipService,
)
from core.services.reports.reports_search_service import KuSearchService
from core.services.reports.reports_submission_service import (
    KuSubmissionService,
)
from core.services.reports.teacher_review_service import TeacherReviewService

__all__ = [
    "KuCoreService",
    "KuProcessingService",
    "KuSearchService",
    "KuSubmissionService",
    "KuRelationshipService",
    "KuSharingService",
    "KuFeedbackService",
    "KuAIInsights",
    "KuProcessingContext",
    "ProgressKuGenerator",
    "KuScheduleService",
    "TeacherReviewService",
]
