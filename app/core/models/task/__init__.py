"""
Task Models - Preserved Types
==============================

Task domain now uses the unified Ku model (core.models.ku).
This package preserves task-specific types that have no Ku equivalent:
- task_request.py - Task API request/response models (Pydantic)
- task_intelligence.py - Task intelligence dataclasses
"""

# Intelligence models
from .task_intelligence import (
    EnergyLevel,
    ProcrastinationTrigger,
    TaskCompletionContext,
    TaskIntelligence,
)
from .task_request import TaskCreateRequest, TaskListResponse, TaskResponse, TaskUpdateRequest

__all__ = [
    "EnergyLevel",
    "ProcrastinationTrigger",
    # API models
    "TaskCompletionContext",
    "TaskCreateRequest",
    # Intelligence models
    "TaskIntelligence",
    "TaskListResponse",
    "TaskResponse",
    "TaskUpdateRequest",
]
