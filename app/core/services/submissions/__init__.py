"""
Submissions Service Package
============================

Sub-services for the Submission stage of SKUEL's educational loop:

    PathStep → Exercise → Submission → Report
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
- SubmissionsSearchService: Generic submission search (date, mood, category, text)
- SubmissionsRelationshipService: Graph relationship creation
- LearningLoopEventHandlerService: Event-driven writes (iteration tracking,
  turnaround calibration, mastery velocity)
- LearningLoopQueryService: Read-side peer — queries that traverse
  Interaction/Exercise/Report edges for the five-phase learning loop

Sharing lives in core.services.sharing (cross-domain).
Report services live in core.services.report.
Journal services live in core.services.journal.
"""

# Learning loop intelligence (event-driven writes + read-side queries)
from core.services.submissions.learning_loop_event_handler_service import (
    LearningLoopEventHandlerService,
)
from core.services.submissions.learning_loop_query_service import LearningLoopQueryService
from core.services.submissions.submissions_core_service import SubmissionsCoreService
from core.services.submissions.submissions_processing_service import SubmissionsProcessingService
from core.services.submissions.submissions_relationship_service import (
    SubmissionsRelationshipService,
)
from core.services.submissions.submissions_search_service import SubmissionsSearchService
from core.services.submissions.submissions_service import SubmissionsService
from core.services.user_entry.assessment_service import AssessmentService

__all__ = [
    "AssessmentService",
    "LearningLoopEventHandlerService",
    "LearningLoopQueryService",
    "SubmissionsCoreService",
    "SubmissionsProcessingService",
    "SubmissionsRelationshipService",
    "SubmissionsSearchService",
    "SubmissionsService",
]
