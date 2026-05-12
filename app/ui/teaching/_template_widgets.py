"""
Custom FormGenerator widgets for Activity Template authoring.

Two widgets specific to the template forms:

- :func:`RelativeOffsetWidget` — three-number row (days/hours/minutes) emitting
  dotted form-field names (``due_offset.days``, ``due_offset.hours``,
  ``due_offset.minutes``) so the submitted body can be reassembled into a
  :class:`RelativeOffsetDTO` shape before Pydantic validation.

- :func:`PsTemplatePicker` — ``<select>`` over the templates of a target type
  already attached to the PathStep. Used for the cross-template-uid fields
  (``fulfills_goal_template_uid``, ``reinforces_habit_template_uid`` …) so the
  teacher cannot type a free-form UID.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, Option, Span

from core.models.templates.relative_offset import RelativeOffset
from ui.forms import Input, Select


def RelativeOffsetWidget(field_name: str, value: Any = None) -> Any:
    """Three side-by-side number inputs for a RelativeOffset field.

    Each input emits a dotted name (``{field}.days`` etc.) so the
    ``parse_template_form_body`` helper can fold them back into the
    ``RelativeOffsetDTO`` shape Pydantic expects.

    Args:
        field_name: The schema field this widget represents (e.g. ``due_offset``).
        value: Existing value to prefill — accepts a :class:`RelativeOffset`,
            a dict with ``days``/``hours``/``minutes`` keys, or ``None``.
    """
    days, hours, minutes = _coerce_offset_value(value)

    def _component(label: str, suffix: str, current: int) -> Any:
        return Div(
            Span(label, cls="text-xs text-muted-foreground mb-1"),
            Input(
                type="number",
                name=f"{field_name}.{suffix}",
                value=str(current),
                min="0",
                full_width=True,
            ),
            cls="flex flex-col flex-1",
        )

    return Div(
        _component("Days", "days", days),
        _component("Hours", "hours", hours),
        _component("Minutes", "minutes", minutes),
        cls="flex gap-2",
    )


def PsTemplatePicker(
    field_name: str,
    options: list[tuple[str, str]],
    value: str | None = None,
) -> Any:
    """``<select>`` of templates attached to the PS, scoped to one target type.

    Args:
        field_name: Schema field this widget represents (e.g.
            ``fulfills_goal_template_uid``).
        options: ``(uid, title)`` pairs — templates of the expected target type
            currently attached to the PS. The route layer fetches these via
            ``service.list_for_pathstep(ps_uid)``.
        value: Existing UID to mark selected.
    """
    placeholder = (
        Option("— none —", value="", selected=value is None)
        if value is None
        else Option("— none —", value="")
    )
    option_nodes = [placeholder]
    for uid, title in options:
        is_selected = uid == value
        option_nodes.append(
            Option(title or uid, value=uid, selected=is_selected) if is_selected
            else Option(title or uid, value=uid)
        )

    if not options:
        # Render a disabled select with a clear hint instead of an empty box,
        # so the teacher knows they need to author the target-type template first.
        return Select(
            Option("(no templates of this type on this PathStep yet)", value=""),
            name=field_name,
            disabled=True,
            full_width=True,
        )

    return Select(*option_nodes, name=field_name, full_width=True)


def _coerce_offset_value(value: Any) -> tuple[int, int, int]:
    """Best-effort extraction of (days, hours, minutes) from a value.

    Accepts :class:`RelativeOffset`, dict, or ``None``. Anything else degrades
    to zero — defensive default keeps the widget renderable even if a future
    schema change passes an unexpected shape.
    """
    if value is None:
        return 0, 0, 0
    if isinstance(value, RelativeOffset):
        return value.days, value.hours, value.minutes
    if isinstance(value, dict):
        return int(value.get("days", 0)), int(value.get("hours", 0)), int(value.get("minutes", 0))
    days = getattr(value, "days", 0) or 0
    hours = getattr(value, "hours", 0) or 0
    minutes = getattr(value, "minutes", 0) or 0
    return int(days), int(hours), int(minutes)


__all__ = ["PsTemplatePicker", "RelativeOffsetWidget"]
