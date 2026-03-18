"""
Form data extraction helpers for type-safe FastHTML form handling.

FastHTML form data can return str | UploadFile | None for any field.
These helpers provide type-safe extraction with proper type guards.

Also provides shared parsing primitives for enum, date, time, and datetime
values used across activity domain UI files.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, TypeVar

from starlette.datastructures import UploadFile

E = TypeVar("E", bound=Enum)


def safe_form_string(value: str | UploadFile | None, default: str = "") -> str:
    """
    Extract string from form data safely.

    Args:
        value: Form field value (may be str, UploadFile, or None)
        default: Default value if extraction fails

    Returns:
        Stripped string value or default

    Example:
        >>> form_data = await request.form()
        >>> username = safe_form_string(form_data.get("username"))
        >>> email = safe_form_string(form_data.get("email"), default="")
    """
    if isinstance(value, str):
        return value.strip()
    return default


def safe_form_int(value: str | UploadFile | None, default: int = 0) -> int:
    """
    Extract integer from form data safely.

    Args:
        value: Form field value (may be str, UploadFile, or None)
        default: Default value if extraction/parsing fails

    Returns:
        Parsed integer or default

    Example:
        >>> age = safe_form_int(form_data.get("age"), default=0)
    """
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def safe_form_bool(value: str | UploadFile | None, default: bool = False) -> bool:
    """
    Extract boolean from form data safely.

    Treats "true", "1", "yes", "on" as True (case-insensitive).

    Args:
        value: Form field value (may be str, UploadFile, or None)
        default: Default value if extraction fails

    Returns:
        Boolean value or default

    Example:
        >>> is_active = safe_form_bool(form_data.get("active"))
    """
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default


# ============================================================================
# Shared Parsing Primitives
# ============================================================================


def parse_enum_safe(enum_class: type[E], value: str | None, default: E) -> E:
    """Parse string to enum, return default on failure.

    Replaces the try/except ValueError pattern duplicated across activity domain UI files.
    """
    if not value:
        return default
    try:
        return enum_class(value)
    except ValueError:
        return default


def parse_date_safe(value: str | None) -> date | None:
    """Parse ISO date string, return None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_time_safe(value: str | None) -> time | None:
    """Parse ISO time string, return None on failure."""
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def parse_datetime_safe(value: str | None) -> datetime | None:
    """Parse ISO datetime string, return None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ============================================================================
# Shared Activity Filters
# ============================================================================


@dataclass
class ActivityFilters:
    """Base filters shared by all 6 Activity Domains.

    Goals, Habits, Events, Choices use this directly (2-field).
    Tasks and Principles extend with domain-specific fields.
    """

    status: str
    sort_by: str

    def to_dict(self) -> dict[str, str]:
        """Convert to dict for view components."""
        return {"status": self.status, "sort_by": self.sort_by}


@dataclass
class TaskFilters(ActivityFilters):
    """Tasks add project, assignee, and due date filtering."""

    project: str = ""
    assignee: str = ""
    due_filter: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to dict keyed for TasksViewComponents.render_list_view."""
        return {
            **super().to_dict(),
            "project": self.project,
            "assignee": self.assignee,
            "due": self.due_filter,
        }


@dataclass
class PrincipleFilters(ActivityFilters):
    """Principles add category and strength filtering."""

    category: str = "all"
    strength: str = "all"

    def to_dict(self) -> dict[str, str]:
        """Convert to dict keyed for PrinciplesViewComponents.render_list_view."""
        return {
            **super().to_dict(),
            "category": self.category,
            "strength": self.strength,
        }


def parse_activity_filters(
    request: Any,
    default_status: str = "active",
    default_sort_by: str = "created_at",
) -> ActivityFilters:
    """Parse standard activity filter params from request query params."""
    return ActivityFilters(
        status=request.query_params.get("filter_status", default_status),
        sort_by=request.query_params.get("sort_by", default_sort_by),
    )


def parse_task_filters(request: Any) -> TaskFilters:
    """Parse task-specific filter params from request query params."""
    return TaskFilters(
        status=request.query_params.get("filter_status", "active"),
        sort_by=request.query_params.get("sort_by", "due_date"),
        project=request.query_params.get("filter_project", ""),
        assignee=request.query_params.get("filter_assignee", ""),
        due_filter=request.query_params.get("filter_due", ""),
    )


def parse_principle_filters(request: Any) -> PrincipleFilters:
    """Parse principle-specific filter params from request query params."""
    return PrincipleFilters(
        status=request.query_params.get("filter_status", "all"),
        sort_by=request.query_params.get("sort_by", "strength"),
        category=request.query_params.get("filter_category", "all"),
        strength=request.query_params.get("filter_strength", "all"),
    )
