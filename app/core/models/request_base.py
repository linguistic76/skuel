"""
Base Request Models
===================

Provides base classes for request models to ensure consistent configuration
and eliminate duplicate model_config declarations.

Usage:
    from core.models.request_base import RequestBase, FilterRequestBase

    class TaskCreateRequest(RequestBase):
        title: str = Field(min_length=1, max_length=200)
        # ... no need for model_config

    class TaskFilterRequest(FilterRequestBase):
        status: KuStatus | None = None
        # ... no need for model_config

Benefits:
- Eliminates ~4 lines of model_config boilerplate per request model
- Ensures consistent Pydantic V2 serialization behavior
- Centralizes configuration changes

Version: 1.0.0
Date: November 28, 2025
"""

from pydantic import BaseModel, ConfigDict


class RequestBase(BaseModel):
    """
    Base class for all request models.

    Configures Pydantic V2 to automatically serialize enums, dates, and datetimes.
    Inherit from this instead of BaseModel for all request models.

    Example:
        class TaskCreateRequest(RequestBase):
            title: str = Field(min_length=1, max_length=200)
            due_date: date | None = None
            priority: Priority = Field(default=Priority.MEDIUM)
    """

    model_config = ConfigDict(
        # Pydantic V2 serializes enums, dates, and datetimes automatically
        # No explicit configuration needed for standard behavior
    )


class FilterRequestBase(RequestBase):
    """
    Base class for filter/query request models.

    Same configuration as RequestBase, but semantically distinct
    to indicate these models are used for filtering/searching.

    Example:
        class TaskFilterRequest(FilterRequestBase):
            status: KuStatus | None = None
            priority: Priority | None = None
            due_date_from: date | None = None
    """

    pass


class AnalyticsRequestBase(RequestBase):
    """
    Base class for analytics request models.

    Provides common fields for analytics/reporting requests.

    Example:
        class HabitAnalyticsRequest(AnalyticsRequestBase):
            include_predictions: bool = Field(default=False)
    """

    pass


class UpdateRequestBase(RequestBase):
    """
    Base class for update request models.

    Update requests typically have all optional fields.
    This base class provides consistent configuration.

    Example:
        class TaskUpdateRequest(UpdateRequestBase):
            title: str | None = None
            description: str | None = None
    """

    pass


class CreateRequestBase(RequestBase):
    """
    Base class for create request models.

    Create requests typically have required and optional fields with defaults.
    This base class provides consistent configuration.

    Example:
        class TaskCreateRequest(CreateRequestBase):
            title: str = Field(min_length=1, max_length=200)
            priority: Priority = Field(default=Priority.MEDIUM)
    """

    pass


class ResponseBase(BaseModel):
    """
    Base class for response models.

    Response models may need from_attributes=True for ORM-style serialization.

    Example:
        class TaskResponse(ResponseBase):
            uid: str
            title: str
            created_at: datetime
    """

    model_config = ConfigDict(
        from_attributes=True,
        # Pydantic V2 serializes enums, dates, and datetimes automatically
    )


class ListResponseBase(ResponseBase):
    """
    Base class for paginated list responses.

    Provides common pagination fields.

    Example:
        class TaskListResponse(ListResponseBase):
            items: list[TaskResponse]
    """

    total: int
    page: int = 1
    page_size: int = 20
