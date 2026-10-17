from typing import Any

import fasthtml.common as fh
from fasthtml.common import Div

from ui.components._util import _cls

__all__ = [
    "Checkbox",
    "Input",
    "Label",
    "LabelCheckbox",
    "LabelInput",
    "LabelSelect",
    "LabelTextArea",
    "Radio",
    "Range",
    "Select",
    "COMPOSER_FOCUS_RING",
    "Switch",
    "TextArea",
]

# Size and look are separate so one keyword can swap the size: a caller's ``cls``
# carries layout only (margin, flex, width caps), never a second height, padding,
# text size, border or background — two utilities for one property are decided by
# their order in output.css, not by the caller. Width is the ``full_width`` flag.
_FIELD_SIZE = "h-11 md:h-10 rounded-md px-3 py-2 text-sm"

# Dense chat chrome (model and scope pickers, the chat-history search and rename
# fields): 44px on phones like every field, 32px with 13px text from ``md`` up.
_FIELD_SIZE_COMPACT = "h-11 md:h-8 rounded-lg px-2.5 py-1 text-13"

_FIELD_LOOK = (
    "flex border border-input bg-background ring-offset-background "
    "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring "
    "focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
)

_INPUT_LOOK = (
    f"{_FIELD_LOOK} file:border-0 file:bg-transparent file:text-sm file:font-medium "
    "placeholder:text-muted-foreground"
)

_TEXTAREA_BASE = (
    "flex min-h-[80px] rounded-md border border-input bg-background px-3 py-2 text-sm "
    "ring-offset-background placeholder:text-muted-foreground focus-visible:outline-hidden "
    "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 "
    "disabled:cursor-not-allowed disabled:opacity-50"
)

# A chat composer is a raw, borderless textarea inside its own bordered box; the
# box carries the focus ring while the textarea has keyboard focus.
COMPOSER_FOCUS_RING = (
    "ring-offset-background has-[textarea:focus-visible]:ring-2 "
    "has-[textarea:focus-visible]:ring-ring has-[textarea:focus-visible]:ring-offset-2"
)

_LABEL_BASE = (
    "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
)


def _aria_attrs(
    name: str,
    help_text: str | None,
    error_text: str | None,
) -> tuple[dict[str, str], list[Any]]:
    """Build ARIA attributes and help/error hint elements for accessible form fields."""
    help_id = f"{name}-help"
    error_id = f"{name}-error"
    extra: dict[str, str] = {}
    elements: list[Any] = []
    describedby_ids: list[str] = []

    if help_text:
        describedby_ids.append(help_id)
        elements.append(Div(help_text, id=help_id, cls="mt-1 text-sm text-muted-foreground"))
    if error_text:
        describedby_ids.append(error_id)
        extra["aria_invalid"] = "true"
        elements.append(
            Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-destructive")
        )
    if describedby_ids:
        extra["aria_describedby"] = " ".join(describedby_ids)

    return extra, elements


def _field_cls(look: str, size: str, *, full_width: bool, error_text: str | None, cls: str) -> str:
    """One field's class list: look, size, exactly one width, then the caller's layout."""
    return _cls(
        look,
        size,
        "w-full" if full_width else "w-auto",
        "border-destructive" if error_text else "",
        cls,
    )


def Label(*c: Any, cls: str = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    """Styled form label."""
    return fh.Label(*c, cls=_cls(_LABEL_BASE, cls), **kwargs)


def Input(
    cls: str = "",
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    compact: bool = False,
    **kwargs: Any,
) -> Any:
    """Styled text input. Wraps in a Div when help_text or error_text is present.

    ``compact`` is the dense chat-chrome size (44px on phones, 32px from ``md``).
    """
    field_cls = _field_cls(
        _INPUT_LOOK,
        _FIELD_SIZE_COMPACT if compact else _FIELD_SIZE,
        full_width=full_width,
        error_text=error_text,
        cls=cls,
    )

    field_name = str(kwargs.get("name", kwargs.get("id", "input")))
    aria_extra, trailing = _aria_attrs(field_name, help_text, error_text)
    kwargs.update(aria_extra)

    element = fh.Input(cls=field_cls, **kwargs)
    if not trailing:
        return element
    return Div(element, *trailing, cls="w-full" if full_width else "")


def TextArea(
    *c: Any,
    cls: str = "",
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """Styled textarea. Wraps in a Div when help_text or error_text is present."""
    field_cls = _field_cls(
        _TEXTAREA_BASE, "", full_width=full_width, error_text=error_text, cls=cls
    )

    field_name = str(kwargs.get("name", kwargs.get("id", "textarea")))
    aria_extra, trailing = _aria_attrs(field_name, help_text, error_text)
    kwargs.update(aria_extra)

    element = fh.Textarea(*c, cls=field_cls, **kwargs)
    if not trailing:
        return element
    return Div(element, *trailing, cls="w-full" if full_width else "")


def Select(
    *options: Any,
    cls: str = "",
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    compact: bool = False,
    **kwargs: Any,
) -> Any:
    """Native <select> with Tailwind styling. Keeps the native element for HTMX form serialization.

    ``compact`` is the dense chat-chrome size (44px on phones, 32px from ``md``).
    """
    field_cls = _field_cls(
        _FIELD_LOOK,
        _FIELD_SIZE_COMPACT if compact else _FIELD_SIZE,
        full_width=full_width,
        error_text=error_text,
        cls=cls,
    )

    field_name = str(kwargs.get("name", kwargs.get("id", "select")))
    aria_extra, trailing = _aria_attrs(field_name, help_text, error_text)
    kwargs.update(aria_extra)

    element = fh.Select(*options, cls=field_cls, **kwargs)
    if not trailing:
        return element
    return Div(element, *trailing, cls="w-full" if full_width else "")


def LabelInput(
    label: str,
    *,
    help_text: str | None = None,
    error_text: str | None = None,
    lbl_cls: str = "",
    cls: str = "space-y-2",
    input_cls: str = "",
    **kwargs: Any,
) -> Any:
    """Label + Input combo with ARIA wiring."""
    element_id = str(kwargs.setdefault("id", str(kwargs.get("name", "input"))))
    return Div(
        Label(label, cls=lbl_cls, fr=element_id),
        Input(cls=input_cls, help_text=help_text, error_text=error_text, **kwargs),
        cls=cls,
    )


def LabelTextArea(
    label: str,
    *,
    help_text: str | None = None,
    error_text: str | None = None,
    lbl_cls: str = "",
    cls: str = "space-y-2",
    input_cls: str = "",
    **kwargs: Any,
) -> Any:
    """Label + TextArea combo with ARIA wiring."""
    element_id = str(kwargs.setdefault("id", str(kwargs.get("name", "textarea"))))
    return Div(
        Label(label, cls=lbl_cls, fr=element_id),
        TextArea(cls=input_cls, help_text=help_text, error_text=error_text, **kwargs),
        cls=cls,
    )


def LabelSelect(
    *options: Any,
    label: str,
    help_text: str | None = None,
    error_text: str | None = None,
    lbl_cls: str = "",
    cls: str = "space-y-2",
    **kwargs: Any,
) -> Any:
    """Label + Select combo with ARIA wiring."""
    element_id = str(kwargs.setdefault("id", str(kwargs.get("name", "select"))))
    return Div(
        Label(label, cls=lbl_cls, fr=element_id),
        Select(*options, help_text=help_text, error_text=error_text, **kwargs),
        cls=cls,
    )


def LabelCheckbox(
    label: str,
    *,
    cls: str = "space-y-2",
    **kwargs: Any,
) -> Any:
    """Label + Checkbox combo."""
    checkbox_id = str(kwargs.pop("id", kwargs.get("name", "checkbox")))
    return Div(
        Div(
            fh.Input(
                type="checkbox", cls="h-4 w-4 rounded-sm border-input", id=checkbox_id, **kwargs
            ),
            Label(label, cls="ml-2", fr=checkbox_id),
            cls="flex items-center",
        ),
        cls=cls,
    )


def Checkbox(cls: str = "", **kwargs: Any) -> Any:
    """Standalone checkbox input (no label). Use LabelCheckbox when a label is needed."""
    return fh.Input(type="checkbox", cls=_cls("h-4 w-4 rounded-sm border-input", cls), **kwargs)


def Switch(cls: str = "", checked: bool = False, **kwargs: Any) -> Any:
    """Toggle switch — visually styled via CSS peer classes on associated label."""
    return fh.Input(
        type="checkbox",
        role="switch",
        cls=_cls("peer sr-only", cls),
        checked=checked,
        **kwargs,
    )


def Radio(cls: str = "", **kwargs: Any) -> Any:
    """Styled radio button."""
    return fh.Input(
        type="radio",
        cls=_cls("h-4 w-4 border-input text-primary focus:ring-ring", cls),
        **kwargs,
    )


def Range(cls: str = "", **kwargs: Any) -> Any:
    """Styled range slider."""
    return fh.Input(
        type="range",
        cls=_cls("w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer", cls),
        **kwargs,
    )
