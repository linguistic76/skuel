"""
API Models
==========

Data models for API requests and responses.
"""

__version__ = "1.0"


from typing import Any

from pydantic import BaseModel


class SKUELResponse(BaseModel):
    """Base response model for SKUEL API"""

    success: bool = True
    data: Any = None
    message: str | None = None


class SKUELErrorResponse(BaseModel):
    """Error response model for SKUEL API"""

    success: bool = False
    error: str
    details: dict[str, Any] | None = None


def create_error_response(error: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create an error response dictionary"""
    response = {"success": False, "error": error}
    if details:
        response["details"] = details
    return response


def create_success_response(data: Any = None, message: str | None = None) -> dict[str, Any]:
    """Create a success response dictionary"""
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if message:
        response["message"] = message
    return response


# Request models for various endpoints
class CreateTaskRequest(BaseModel):
    """Request model for creating a task"""

    title: str
    description: str | None = None
    priority: str | None = "medium"
    tags: list[str] | None = []


# Alias for consistency
TaskCreateRequest = CreateTaskRequest


class UpdateTaskRequest(BaseModel):
    """Request model for updating a task"""

    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    tags: list[str] | None = None


# Alias for consistency
TaskUpdateRequest = UpdateTaskRequest


class CreateTransactionRequest(BaseModel):
    """Request model for creating a transaction"""

    amount: float
    description: str
    category: str | None = None
    date: str | None = None


class SyncRequest(BaseModel):
    """Request model for sync operations"""

    domains: list[str] | None = None
    force: bool = False


class HabitCreateRequest(BaseModel):
    """Request model for creating a habit"""

    name: str
    description: str | None = None
    frequency: str | None = "daily"
    target_count: int | None = 1


class HabitUpdateRequest(BaseModel):
    """Request model for updating a habit"""

    name: str | None = None
    description: str | None = None
    frequency: str | None = None
    target_count: int | None = None
    is_active: bool | None = None


class TimelineEventRequest(BaseModel):
    """Request model for timeline events"""

    title: str
    timestamp: str | None = None
    type: str | None = "event"
