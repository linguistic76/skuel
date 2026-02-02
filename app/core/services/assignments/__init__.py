"""
Assignments Service Sub-Services
=================================

This package contains focused sub-services for the Assignments domain.

Architecture: Processing Domain (not Activity Domain)
- Handles file submission, processing pipelines, and content management
- Different from Activity domains (Tasks, Goals, etc.) which use facade pattern
- Shares patterns with Journals domain

Sub-services:
- AssignmentsSubmissionService: File upload and storage
- AssignmentsProcessingService: Processing orchestration (audio, text, future: PDF, image)
- AssignmentsCoreService: Content management (categories, tags, status workflow)
- AssignmentsSearchService: Query and search operations
- AssignmentsRelationshipService: Graph relationship creation

Domain Separation (January 2026):
- Assignments: File submission, teacher review, processing
- Journals: Personal reflections, separate processing pipeline

Version: 1.0.0
Date: 2026-01-21
"""

from core.services.assignments.assignment_sharing_service import (
    AssignmentSharingService,
)
from core.services.assignments.assignments_core_service import AssignmentsCoreService
from core.services.assignments.assignments_processing_service import (
    AssignmentProcessorService,
)
from core.services.assignments.assignments_relationship_service import (
    AssignmentRelationshipService,
)
from core.services.assignments.assignments_search_service import AssignmentsQueryService
from core.services.assignments.assignments_submission_service import (
    AssignmentSubmissionService,
)

__all__ = [
    # Primary names (new standardized)
    "AssignmentsCoreService",
    "AssignmentsProcessingService",
    "AssignmentsSearchService",
    "AssignmentsSubmissionService",
    "AssignmentsRelationshipService",
    "AssignmentSharingService",
    # Backward compatibility aliases (class names unchanged for now)
    "AssignmentProcessorService",
    "AssignmentRelationshipService",
    "AssignmentSubmissionService",
    "AssignmentsQueryService",
]

# Aliases for backward compatibility during transition
# These can be removed once all consumers are updated
AssignmentsProcessingService = AssignmentProcessorService
AssignmentsSearchService = AssignmentsQueryService
AssignmentsSubmissionService = AssignmentSubmissionService
AssignmentsRelationshipService = AssignmentRelationshipService
