"""
Form data extraction helpers for type-safe FastHTML form handling.

FastHTML form data can return str | UploadFile | None for any field.
These helpers provide type-safe extraction with proper type guards.

Also provides shared parsing primitives for enum, date, time, and datetime
values used across activity domain UI files.
"""

import types
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile

from adapters.inbound.fasthtml_types import Request
from core.utils.result_simplified import Errors, Result


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


def parse_enum_safe[E: Enum](enum_class: type[E], value: str | None, default: E) -> E:
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
# Request Body Parsing — JSON and Form Data → Pydantic Model
# ============================================================================


async def parse_json_body[T: BaseModel](
    request: Request,
    schema: type[T],
    extra: dict[str, Any] | None = None,
) -> Result[T]:
    """Parse JSON request body into a Pydantic model, returning Result[T].

    Replaces the repeated try/except ValidationError pattern across API routes.

    Args:
        request: Starlette/FastHTML request
        schema: Pydantic model class to validate against
        extra: Optional extra fields to merge into body before validation
               (e.g., ``{"habit_uid": entity.uid}``)

    Returns:
        Result.ok(model) on success, Result.fail(validation error) on failure

    Example::

        result = await parse_json_body(request, SubmitReportRequest)
        if result.is_error:
            return result
        req = result.value
    """
    try:
        body = await request.json()
    except Exception:  # safety-net: JSON parsing boundary
        return Result.fail(Errors.validation("Invalid JSON body"))

    if extra:
        body = {**body, **extra}

    try:
        return Result.ok(schema.model_validate(body))
    except ValidationError as e:
        return Result.fail(Errors.validation(str(e), field="body"))


def _list_field_names(schema: type[BaseModel]) -> set[str]:
    """Field names whose annotation is ``list[T]`` or ``Optional[list[T]]``.

    Mirrors FormGenerator's textarea-for-list mapping so list values posted as
    a single newline-delimited string can be split back into a list before
    Pydantic validation.
    """
    names: set[str] = set()
    for name, field in schema.model_fields.items():
        ann = field.annotation
        if ann is None:
            continue
        if get_origin(ann) is list:
            names.add(name)
            continue
        origin = get_origin(ann)
        if origin is Union or origin is types.UnionType:
            for arg in get_args(ann):
                if get_origin(arg) is list:
                    names.add(name)
                    break
    return names


def _split_list_input(value: str) -> list[str]:
    """Split a textarea string into trimmed, non-empty items.

    Splits on newlines (FormGenerator's render format); falls back to commas
    for inputs typed on a single line.
    """
    if not value:
        return []
    parts = value.splitlines() if "\n" in value else value.split(",")
    return [p.strip() for p in parts if p.strip()]


async def parse_form_body[T: BaseModel](
    request: Request,
    schema: type[T],
) -> Result[T]:
    """Parse form data into a Pydantic model, returning Result[T].

    Converts form fields to a dict (stripping strings, passing UploadFile through)
    then validates via Pydantic. Empty strings become None so optional fields work
    naturally. Fields declared as ``list[T]`` (or ``Optional[list[T]]``) are split
    from the textarea string back into a list.

    Args:
        request: Starlette/FastHTML request
        schema: Pydantic model class to validate against

    Returns:
        Result.ok(model) on success, Result.fail(validation error) on failure

    Example::

        result = await parse_form_body(request, CreateTeachingExerciseRequest)
        if result.is_error:
            return result
        req = result.value
    """
    form = await request.form()
    list_fields = _list_field_names(schema)
    data: dict[str, Any] = {}
    for key in form:
        value = form[key]
        if isinstance(value, UploadFile):
            data[key] = value
        elif isinstance(value, str):
            stripped = value.strip()
            if key in list_fields:
                data[key] = _split_list_input(stripped)
            else:
                data[key] = stripped if stripped else None
        else:
            data[key] = value

    try:
        return Result.ok(schema.model_validate(data))
    except ValidationError as e:
        return Result.fail(Errors.validation(str(e), field="body"))


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
    request: Request,
    default_status: str = "active",
    default_sort_by: str = "created_at",
) -> ActivityFilters:
    """Parse standard activity filter params from request query params."""
    return ActivityFilters(
        status=request.query_params.get("filter_status", default_status),
        sort_by=request.query_params.get("sort_by", default_sort_by),
    )


def parse_task_filters(request: Request) -> TaskFilters:
    """Parse task-specific filter params from request query params."""
    return TaskFilters(
        status=request.query_params.get("filter_status", "active"),
        sort_by=request.query_params.get("sort_by", "due_date"),
        project=request.query_params.get("filter_project", ""),
        assignee=request.query_params.get("filter_assignee", ""),
        due_filter=request.query_params.get("filter_due", ""),
    )


def parse_principle_filters(request: Request) -> PrincipleFilters:
    """Parse principle-specific filter params from request query params."""
    return PrincipleFilters(
        status=request.query_params.get("filter_status", "all"),
        sort_by=request.query_params.get("sort_by", "strength"),
        category=request.query_params.get("filter_category", "all"),
        strength=request.query_params.get("filter_strength", "all"),
    )
