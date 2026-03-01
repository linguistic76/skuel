"""
Submissions Service Package
============================

Sub-services for the Submission stage of SKUEL's educational loop:

    Ku → Exercise → Submission → Feedback
                         ↑
               student produces work

Architecture: Content/Processing Domain (not Activity Domain)
- Handles file upload, processing pipelines, content management, and journals
- EntityType.SUBMISSION + EntityType.JOURNAL (both are student work products)

Sub-services:
- SubmissionsService: File upload and storage
- SubmissionsProcessingService: Processing orchestration (audio, text, PDF)
- SubmissionsCoreService: Content management + journal CRUD
- SubmissionsSearchService: Query and search operations
- SubmissionsRelationshipService: Graph relationship creation

Sharing lives in core.services.sharing (cross-domain).
Feedback services live in core.services.feedback.
"""

from core.services.submissions.journal_output_generator import JournalOutputGenerator
from core.services.submissions.submission_processing_types import (
    SubmissionAIInsights,
    SubmissionProcessingContext,
)
from core.services.submissions.submissions_core_service import SubmissionsCoreService
from core.services.submissions.submissions_processing_service import SubmissionsProcessingService
from core.services.submissions.submissions_relationship_service import (
    SubmissionsRelationshipService,
)
from core.services.submissions.submissions_search_service import SubmissionsSearchService
from core.services.submissions.submissions_service import SubmissionsService

__all__ = [
    "JournalOutputGenerator",
    "SubmissionAIInsights",
    "SubmissionProcessingContext",
    "SubmissionsCoreService",
    "SubmissionsProcessingService",
    "SubmissionsRelationshipService",
    "SubmissionsSearchService",
    "SubmissionsService",
]
