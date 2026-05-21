"""
Form-body parsing for Activity Template requests.

The template request schemas embed :class:`RelativeOffsetDTO` for fields like
``due_offset`` / ``start_offset``. The HTML form renders each offset as three
numeric inputs named ``{field}.days`` / ``{field}.hours`` / ``{field}.minutes``
(see :func:`ui.teaching._template_widgets.RelativeOffsetWidget`). This module
collapses the dotted keys back into nested dicts before Pydantic validation.

Empty offsets (all three components zero) are coerced to ``None`` so optional
offset fields stay optional instead of being persisted as a no-op offset.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile

from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import _list_field_names, _split_list_input
from core.utils.result_simplified import Errors, Result

_OFFSET_COMPONENTS = ("days", "hours", "minutes")


async def parse_template_form_body[T: BaseModel](
    request: Request,
    schema: type[T],
) -> Result[T]:
    """Parse a template form body, folding dotted offset keys into nested dicts.

    Mirrors :func:`adapters.inbound.form_helpers.parse_form_body` for the flat
    fields, then post-processes any ``{field}.{component}`` keys into the
    ``{days, hours, minutes}`` shape Pydantic expects for
    :class:`RelativeOffsetDTO`.

    Returns ``Result.fail(validation error)`` on Pydantic failure, never raises.
    """
    form = await request.form()
    list_fields = _list_field_names(schema)
    data: dict[str, Any] = {}
    offsets: dict[str, dict[str, int]] = {}

    for key in form:
        value = form[key]
        if "." in key:
            field, _, component = key.partition(".")
            if component in _OFFSET_COMPONENTS and isinstance(value, str):
                try:
                    offsets.setdefault(field, {})[component] = int(value or "0")
                except ValueError:
                    return Result.fail(
                        Errors.validation(
                            message=f"{field}.{component} must be a non-negative integer",
                            field=field,
                        )
                    )
            continue

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

    for field, components in offsets.items():
        days = components.get("days", 0)
        hours = components.get("hours", 0)
        minutes = components.get("minutes", 0)
        if days == 0 and hours == 0 and minutes == 0:
            data[field] = None
        else:
            data[field] = {"days": days, "hours": hours, "minutes": minutes}

    try:
        return Result.ok(schema.model_validate(data))
    except ValidationError as exc:
        return Result.fail(Errors.validation(str(exc), field="body"))


__all__ = ["parse_template_form_body"]
