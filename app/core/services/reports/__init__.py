"""
Reports Service Sub-Services
=================================

This package contains focused sub-services for the Reports domain.

Architecture: Processing Domain (not Activity Domain)
- Handles file submission, processing pipelines, content management, and journals
- Different from Activity domains (Tasks, Goals, etc.) which use facade pattern
- Journals merged into Reports (February 2026) — journal is a ReportType

Sub-services:
- ReportsSubmissionService: File upload and storage
- ReportsProcessingService: Processing orchestration (audio, text, future: PDF, image)
- ReportsCoreService: Content management + journal CRUD
- ReportsSearchService: Query and search operations
- ReportsRelationshipService: Graph relationship creation
- ReportSharingService: Content sharing between users
- ReportFeedbackService: AI feedback generation via ReportProject
- ReportProjectService: LLM instruction project management
"""

from core.services.reports.report_feedback_service import ReportFeedbackService
from core.services.reports.report_processing_types import (
    ReportAIInsights,
    ReportProcessingContext,
)
from core.services.reports.report_project_service import ReportProjectService
from core.services.reports.report_sharing_service import (
    ReportSharingService,
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
    ReportSubmissionService,
)

__all__ = [
    "ReportsCoreService",
    "ReportsProcessingService",
    "ReportsSearchService",
    "ReportSubmissionService",
    "ReportsRelationshipService",
    "ReportSharingService",
    "ReportFeedbackService",
    "ReportProjectService",
    "ReportAIInsights",
    "ReportProcessingContext",
]
