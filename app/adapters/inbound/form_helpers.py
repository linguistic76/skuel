"""
Form data extraction helpers for type-safe FastHTML form handling.

FastHTML form data can return str | UploadFile | None for any field.
These helpers provide type-safe extraction with proper type guards.

Also provides the request-body readers (``parse_body``, ``parse_json_body``,
``parse_form_body``) that validate a body into a Pydantic model as a ``Result``.
"""

import types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from python_multipart.exceptions import MultipartParseError
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
# Request Body Parsing — JSON and Form Data → Pydantic Model
# ============================================================================


async def parse_json_body[T: BaseModel](
    request: Request,
    schema: type[T],
) -> Result[T]:
    """Parse JSON request body into a Pydantic model, returning Result[T].

    Replaces the repeated try/except ValidationError pattern across API routes.

    Args:
        request: Starlette/FastHTML request
        schema: Pydantic model class to validate against

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

    return _validate_body(schema, body)


def _validate_body[T: BaseModel](schema: type[T], data: object) -> Result[T]:
    """Pydantic validation as a ``Result`` — the one seam every body parser ends in."""
    try:
        return Result.ok(schema.model_validate(data))
    except ValidationError as e:
        return Result.fail(Errors.validation(str(e), field="body"))


#: Media types a browser form posts with. Everything else is read as JSON.
FORM_MEDIA_TYPES = frozenset({"application/x-www-form-urlencoded", "multipart/form-data"})


def media_type_of(request: Request) -> str:
    """The Content-Type's media type alone — ``application/json; charset=utf-8`` → ``application/json``."""
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


async def parse_body[T: BaseModel](
    request: Request,
    schema: type[T],
) -> Result[T]:
    """Parse the request body into a Pydantic model by its ``Content-Type``.

    One write door serves two caller kinds: an API client posts JSON, and an HTMX
    form or button posts url-encoded (or multipart) — htmx encodes every body that
    way, whatever ``hx-headers`` claims. The header decides which reader runs, as it
    does in FastHTML's own parameter extraction: a form media type goes through
    :func:`parse_form_body` (empty strings → ``None``, ``list[T]`` fields split from
    the textarea string), anything else through :func:`parse_json_body`. A body with
    no bytes at all is the empty field set, ``{}``, whatever type it declares — a
    bare POST with nothing to say — and the schema decides whether nothing is enough.

    Use this at a route both kinds reach (the CRUD factory's create/update, the admin
    account actions); a JSON-only API route may keep ``parse_json_body`` and a
    form-only UI route ``parse_form_body``.

    Example::

        parsed = await parse_body(request, ExerciseCreateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
    """
    if media_type_of(request) in FORM_MEDIA_TYPES:
        return await parse_form_body(request, schema)
    if not await request.body():
        return _validate_body(schema, {})
    return await parse_json_body(request, schema)


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
    """Split a textarea string into trimmed, non-empty items — one per line.

    Lines are the one delimiter, because they are what the textarea renders a
    stored list back as (FormGenerator joins on newlines): a stored item that
    contains a comma must survive an unrelated save as one item.
    """
    if not value:
        return []
    return [p.strip() for p in value.splitlines() if p.strip()]


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

        result = await parse_form_body(request, ExerciseCreateRequest)
        if result.is_error:
            return result
        req = result.value
    """
    try:
        form = await request.form()
    except MultipartParseError:
        # FastHTML reads most multipart bodies during parameter extraction (where
        # the app-level guard answers); a body it skipped as too short to hold a
        # part is first read here, and its syntax is the client's error too.
        return Result.fail(Errors.validation("Malformed multipart form data in request body"))
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

    return _validate_body(schema, data)
