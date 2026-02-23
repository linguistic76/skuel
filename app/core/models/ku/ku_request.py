"""
Unified Knowledge Request Models — Re-Export Shim
===================================================

This file re-exports all request models from their new domain-specific homes.
Import sites can continue using `from core.models.ku.ku_request import ...`
until they are migrated to import from the specific files directly.

Canonical locations:
    activity_requests.py    — Activity domain creates (Tasks, Goals, etc.)
    curriculum_requests.py  — Curriculum creates (KU, LS, LP)
    report_requests.py      — Report creates + LifePath + Assessment
    entity_requests.py      — Shared types (update, response, bulk ops)
"""

# --- Activity domain requests ---
from core.models.ku.activity_requests import (
    AlignmentAssessmentRequest,
    ChoiceCreateRequest,
    ChoiceDecisionRequest,
    ChoiceEvaluationRequest,
    ChoiceOptionCreateRequest,
    ChoiceOptionRequest,
    ChoiceOptionUpdateRequest,
    EventCreateRequest,
    GoalCreateRequest,
    HabitCreateRequest,
    MilestoneRequest,
    PrincipleAlignmentAssessmentResult,
    PrincipleCreateRequest,
    PrincipleExpressionRequest,
    PrincipleFilterRequest,
    PrincipleLinkRequest,
    TaskCreateRequest,
)

# --- Curriculum domain requests ---
from core.models.ku.curriculum_requests import (
    CurriculumCreateRequest,
    LearningPathCreateRequest,
    LearningPathFilterRequest,
    LearningPathProgressRequest,
    LearningStepCreateRequest,
    MocCreateRequest,
)

# --- Entity-wide requests (shared across domains) ---
from core.models.ku.entity_requests import (
    AddTagsRequest,
    BulkCategorizeRequest,
    BulkDeleteRequest,
    BulkTagRequest,
    CategorizeEntityRequest,
    EntityListResponse,
    EntityResponse,
    EntityUpdateRequest,
    ProgressReportGenerateRequest,
    RemoveTagsRequest,
    ScheduleCreateRequest,
    ScheduleUpdateRequest,
)

# --- Report domain requests ---
from core.models.ku.report_requests import (
    AiReportCreateRequest,
    AssessmentCreateRequest,
    FeedbackCreateRequest,
    LifePathCreateRequest,
    SubmissionCreateRequest,
)

__all__ = [
    # Nested request models
    "MilestoneRequest",
    "ChoiceOptionRequest",
    "PrincipleExpressionRequest",
    # Activity domain creates
    "TaskCreateRequest",
    "GoalCreateRequest",
    "HabitCreateRequest",
    "EventCreateRequest",
    "ChoiceCreateRequest",
    "ChoiceEvaluationRequest",
    "ChoiceDecisionRequest",
    "ChoiceOptionCreateRequest",
    "ChoiceOptionUpdateRequest",
    "PrincipleCreateRequest",
    "AlignmentAssessmentRequest",
    "PrincipleLinkRequest",
    "PrincipleFilterRequest",
    "PrincipleAlignmentAssessmentResult",
    # Content processing creates
    "CurriculumCreateRequest",
    "SubmissionCreateRequest",
    "AiReportCreateRequest",
    "FeedbackCreateRequest",
    # Curriculum creates
    "MocCreateRequest",
    "LearningStepCreateRequest",
    "LearningPathCreateRequest",
    "LearningPathFilterRequest",
    "LearningPathProgressRequest",
    # Destination
    "LifePathCreateRequest",
    # Update/Response
    "EntityUpdateRequest",
    "EntityResponse",
    "EntityListResponse",
    # Route-specific
    "CategorizeEntityRequest",
    "AddTagsRequest",
    "RemoveTagsRequest",
    "BulkCategorizeRequest",
    "BulkTagRequest",
    "BulkDeleteRequest",
    "ProgressReportGenerateRequest",
    "ScheduleCreateRequest",
    "ScheduleUpdateRequest",
    "AssessmentCreateRequest",
]
