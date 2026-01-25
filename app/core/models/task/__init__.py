"""
Task Models - Three-Tier Architecture
======================================

Clean three-tier model structure for Tasks:

1. task_request.py - External API models (Pydantic)
2. task_dto.py - Data transfer objects (Mutable)
3. task.py - Domain models with business logic (Immutable)

Usage:
    from core.models.task import Task, TaskDTO, TaskCreateRequest
"""

from .task import Task
from .task_dto import TaskDTO

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
    # Domain model
    "Task",
    "TaskCompletionContext",
    # API models
    "TaskCreateRequest",
    # Transfer object
    "TaskDTO",
    # Intelligence models
    "TaskIntelligence",
    "TaskListResponse",
    "TaskResponse",
    "TaskUpdateRequest",
]
