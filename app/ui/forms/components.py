"""
SKUEL Form Components (MonsterUI)
==================================

Form component wrappers using MonsterUI internals.
Keeps SKUEL's API (Input, Select, Textarea, FormControl, Label, Checkbox, etc.).
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import Div, Span
from fasthtml.common import Input as FTInput
from monsterui.franken import CheckboxX as MCheckbox
from monsterui.franken import FormLabel as MFormLabel
from monsterui.franken import Input as MInput
from monsterui.franken import Radio as MRadio
from monsterui.franken import Range as MRange
from monsterui.franken import Select as MSelect
from monsterui.franken import Switch as MSwitch
from monsterui.franken import TextArea as MTextArea

from ui.buttons import ButtonT
from ui.layout import Size

__all__ = [
    "InputT",
    "Input",
    "Select",
    "Textarea",
    "FormControl",
    "Label",
    "LabelText",
    "Checkbox",
    "Radio",
    "Toggle",
    "Range",
]


class InputT(StrEnum):
    """Input variant types — kept for API compatibility.

    MonsterUI inputs don't have variant classes like DaisyUI's input-bordered etc.
    The variant parameter is accepted but styling comes from the MonsterUI theme.
    """

    bordered = "bordered"
    ghost = "ghost"
    primary = "primary"
    secondary = "secondary"
    accent = "accent"
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"


def Input(
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Input wrapper using MonsterUI.

    Args:
        cls: Additional CSS classes
        variant: Input style variant (kept for API compat; MonsterUI uses theme styling)
        size: Input size (xs, sm, md, lg)
        full_width: If True, input takes full width
        help_text: Optional help text displayed below the input
        error_text: Optional error message displayed below the input
        **kwargs: Additional HTML attributes (type, name, value, placeholder, id, etc.)
    """
    cls_parts = []
    if full_width:
        cls_parts.append("w-full")
    if variant == InputT.error or error_text:
        cls_parts.append("border-destructive")
    if cls:
        cls_parts.append(cls)

    # Build ARIA attributes if help or error text provided
    input_name = kwargs.get("name", kwargs.get("id", "input"))
    help_id = f"{input_name}-help"
    error_id = f"{input_name}-error"
    describedby_ids = []

    if help_text:
        describedby_ids.append(help_id)
    if error_text:
        describedby_ids.append(error_id)
        kwargs["aria_invalid"] = "true"

    if describedby_ids:
        kwargs["aria_describedby"] = " ".join(describedby_ids)

    input_element = MInput(cls=" ".join(cls_parts) if cls_parts else None, **kwargs)

    # If no help or error text, return just the input (backward compatible)
    if not help_text and not error_text:
        return input_element

    # Otherwise, wrap with help/error text
    elements = [input_element]

    if help_text:
        elements.append(
            Div(help_text, id=help_id, cls="mt-1 text-sm text-muted-foreground")
        )

    if error_text:
        elements.append(
            Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-destructive")
        )

    return Div(*elements, cls="w-full" if full_width else "")


def Select(
    *options: Any,
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Select wrapper using MonsterUI.

    Args:
        *options: Option elements
        cls: Additional CSS classes
        variant: Select style variant (kept for API compat)
        size: Select size (xs, sm, md, lg)
        full_width: If True, select takes full width
        help_text: Optional help text displayed below the select
        error_text: Optional error message displayed below the select
        **kwargs: Additional HTML attributes (name, required, id, etc.)
    """
    cls_parts = []
    if full_width:
        cls_parts.append("w-full")
    if variant == InputT.error or error_text:
        cls_parts.append("border-destructive")
    if cls:
        cls_parts.append(cls)

    # Build ARIA attributes
    select_name = kwargs.get("name", kwargs.get("id", "select"))
    help_id = f"{select_name}-help"
    error_id = f"{select_name}-error"
    describedby_ids = []

    if help_text:
        describedby_ids.append(help_id)
    if error_text:
        describedby_ids.append(error_id)
        kwargs["aria_invalid"] = "true"

    if describedby_ids:
        kwargs["aria_describedby"] = " ".join(describedby_ids)

    select_element = MSelect(*options, cls=" ".join(cls_parts) if cls_parts else None, **kwargs)

    if not help_text and not error_text:
        return select_element

    elements = [select_element]

    if help_text:
        elements.append(
            Div(help_text, id=help_id, cls="mt-1 text-sm text-muted-foreground")
        )

    if error_text:
        elements.append(
            Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-destructive")
        )

    return Div(*elements, cls="w-full" if full_width else "")


def Textarea(
    *c: Any,
    cls: str = "",
    variant: InputT = InputT.bordered,
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Textarea wrapper using MonsterUI.

    Args:
        *c: Initial textarea content
        cls: Additional CSS classes
        variant: Textarea style variant (kept for API compat)
        size: Textarea size (xs, sm, md, lg)
        full_width: If True, textarea takes full width
        help_text: Optional help text displayed below the textarea
        error_text: Optional error message displayed below the textarea
        **kwargs: Additional HTML attributes (name, rows, placeholder, id, etc.)
    """
    cls_parts = []
    if full_width:
        cls_parts.append("w-full")
    if variant == InputT.error or error_text:
        cls_parts.append("border-destructive")
    if cls:
        cls_parts.append(cls)

    # Build ARIA attributes
    textarea_name = kwargs.get("name", kwargs.get("id", "textarea"))
    help_id = f"{textarea_name}-help"
    error_id = f"{textarea_name}-error"
    describedby_ids = []

    if help_text:
        describedby_ids.append(help_id)
    if error_text:
        describedby_ids.append(error_id)
        kwargs["aria_invalid"] = "true"

    if describedby_ids:
        kwargs["aria_describedby"] = " ".join(describedby_ids)

    textarea_element = MTextArea(
        *c, cls=" ".join(cls_parts) if cls_parts else None, **kwargs
    )

    if not help_text and not error_text:
        return textarea_element

    elements = [textarea_element]

    if help_text:
        elements.append(
            Div(help_text, id=help_id, cls="mt-1 text-sm text-muted-foreground")
        )

    if error_text:
        elements.append(
            Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-destructive")
        )

    return Div(*elements, cls="w-full" if full_width else "")


def FormControl(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Form control wrapper for proper form layout.

    Args:
        *c: Form control content (label, input, helper text)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["space-y-2"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Label(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Form label wrapper using MonsterUI FormLabel.

    Args:
        *c: Label content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    return MFormLabel(*c, cls=cls or None, **kwargs)


def LabelText(*c: Any, cls: str = "", alt: bool = False, **kwargs: Any) -> Any:
    """
    Label text wrapper.

    Args:
        *c: Label text content
        cls: Additional CSS classes
        alt: If True, uses smaller muted text
        **kwargs: Additional HTML attributes
    """
    classes = ["text-xs text-muted-foreground" if alt else "text-sm font-medium"]
    if cls:
        classes.append(cls)
    return Span(*c, cls=" ".join(classes), **kwargs)


def Checkbox(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    Checkbox wrapper using MonsterUI.

    Args:
        cls: Additional CSS classes
        variant: Checkbox color variant (kept for API compat)
        size: Checkbox size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    return MCheckbox(cls=cls or None, **kwargs)


def Radio(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    Radio button wrapper using MonsterUI.

    Args:
        cls: Additional CSS classes
        variant: Radio color variant (kept for API compat)
        size: Radio size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    return MRadio(cls=cls or None, **kwargs)


def Toggle(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    Toggle/Switch wrapper using MonsterUI's Switch component.

    Args:
        cls: Additional CSS classes
        variant: Toggle color variant (kept for API compat)
        size: Toggle size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    return MSwitch(cls=cls or None, **kwargs)


def Range(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    Range slider wrapper using MonsterUI.

    Args:
        cls: Additional CSS classes
        variant: Range color variant (kept for API compat)
        size: Range size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes (min, max, value, step)
    """
    return MRange(cls=cls or None, **kwargs)
