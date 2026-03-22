"""
Submissions Service Package
============================

Sub-services for the Submission stage of SKUEL's educational loop:

    Lesson → Exercise → Submission → Report
                         ↑
               student produces work

Architecture: Content/Processing Domain (not Activity Domain)
- Handles file upload, processing pipelines, content management
- EntityType.EXERCISE_SUBMISSION (student work products)
- Journal domain (JE_INPUT/JE_OUTPUT) extracted to core.services.journal

Sub-services:
- SubmissionsService: File upload and storage
- SubmissionsProcessingService: Processing orchestration (audio, text, PDF)
- SubmissionsCoreService: Content management facade (delegates assessment)
  - AssessmentService: Teacher assessment CRUD, authority verification
- SubmissionsSearchService: Query and search operations
- SubmissionsRelationshipService: Graph relationship creation

Sharing lives in core.services.sharing (cross-domain).
Report services live in core.services.report.
Journal services live in core.services.journal.
"""

from core.services.submissions.assessment_service import AssessmentService

# Learning loop intelligence (event-driven insights)
from core.services.submissions.learning_loop_event_handler_service import (
    LearningLoopEventHandlerService,
)
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
    "AssessmentService",
    "LearningLoopEventHandlerService",
    "SubmissionAIInsights",
    "SubmissionProcessingContext",
    "SubmissionsCoreService",
    "SubmissionsProcessingService",
    "SubmissionsRelationshipService",
    "SubmissionsSearchService",
    "SubmissionsService",
]
