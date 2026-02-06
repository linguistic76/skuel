"""
Reports Service Sub-Services
=================================

This package contains focused sub-services for the Reports domain.

Architecture: Processing Domain (not Activity Domain)
- Handles file submission, processing pipelines, and content management
- Different from Activity domains (Tasks, Goals, etc.) which use facade pattern
- Shares patterns with Journals domain

Sub-services:
- ReportsSubmissionService: File upload and storage
- ReportsProcessingService: Processing orchestration (audio, text, future: PDF, image)
- ReportsCoreService: Content management (categories, tags, status workflow)
- ReportsSearchService: Query and search operations
- ReportsRelationshipService: Graph relationship creation

Domain Separation (January 2026):
- Reports: File submission, teacher review, processing
- Journals: Personal reflections, separate processing pipeline

Version: 1.0.0
Date: 2026-01-21
"""

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
]
